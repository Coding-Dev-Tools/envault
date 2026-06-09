"""HTTP API server for exposing decrypted secrets as a JSON API.

Endpoints:
 GET /secrets -> list all secret keys (or filter by ?prefix=FOO)
 GET /secrets/{key} -> get decrypted value for a specific key
 GET /health -> connectivity check for the backing store

Security:
 - Default bind address is 127.0.0.1 (localhost only).
 - If --api-key is provided, all endpoints (except /health) require
   an Authorization: Bearer <api-key> header. Requests without a
   valid token receive 401 Unauthorized.
 - If --api-key is not provided, a warning is printed at startup
   recommending authentication for production use.
"""

from __future__ import annotations

import json
import os
import secrets as _secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

from envault.config import EnvaultConfig, SecretStoreConfig
from envault.encrypt import KEY_ENV_VAR
from envault.stores import SecretStore, LocalEnvStore, get_store

# Environment variable for API authentication key
API_KEY_ENV_VAR = "ENVAULT_API_KEY"


class SecretHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the envault secrets API."""

    # Set by run_server() before the server starts
    store: SecretStore
    config: EnvaultConfig
    encrypt_key: str | None
    api_key: str | None  # Bearer token for API auth; None = auth disabled

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Serialize *data* as JSON and send it with the appropriate headers."""
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        """Send a JSON error payload."""
        self._send_json({"error": message}, status=status)

    def _check_auth(self) -> bool:
        """Validate the Bearer token if API auth is enabled.

        Returns True if the request is authorized (or auth is disabled).
        Returns False if auth is required but missing/invalid (and sends 401).
        """
        if not self.api_key:
            # Auth not configured — allow all requests
            return True

        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):]
            if _secrets.compare_digest(token, self.api_key):
                return True

        self._send_error(401, "Unauthorized: valid Bearer token required")
        return False

    # ── Routing ──────────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802 – stdlib naming convention
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if path == "/health":
            # /health is always accessible (useful for load balancers)
            self._handle_health()
        elif path == "/secrets":
            if not self._check_auth():
                return
            self._handle_secrets_list(query)
        elif path.startswith("/secrets/"):
            if not self._check_auth():
                return
            key = path[len("/secrets/"):]
            self._handle_secrets_get(key)
        else:
            self._send_error(404, "Not found")

    # ── Endpoints ────────────────────────────────────────────────────────────

    def _handle_health(self) -> None:
        """GET /health — connectivity check for the backing store."""
        store = self.store
        checks: dict[str, Any] = {}

        if isinstance(store, LocalEnvStore):
            env_file = Path(store.env_file)
            checks["local"] = {
                "status": "ok" if env_file.exists() else "error",
                "path": str(env_file),
            }
        else:
            # For cloud stores we attempt a lightweight list_keys call.
            # If it succeeds (even returning empty) the store is reachable.
            store_type = type(store).__name__
            try:
                store.list_keys()
                checks[store_type] = {"status": "ok"}
            except Exception as exc:
                checks[store_type] = {"status": "error", "detail": str(exc)}

        overall = "ok" if all(c.get("status") == "ok" for c in checks.values()) else "error"
        self._send_json({"status": overall, "checks": checks})

    def _handle_secrets_list(self, query: dict[str, list[str]]) -> None:
        """GET /secrets — list keys, optionally filtered by ?prefix=."""
        prefix = query.get("prefix", [""])[0]
        try:
            keys = self.store.list_keys(prefix=prefix)
        except Exception as exc:
            self._send_error(500, f"Failed to list keys: {exc}")
            return
        self._send_json({"keys": keys, "count": len(keys)})

    def _handle_secrets_get(self, key: str) -> None:
        """GET /secrets/{key} — get decrypted value for a single key."""
        if not key:
            self._send_error(400, "Key is required")
            return
        try:
            value = self.store.get(key)
        except Exception as exc:
            self._send_error(500, f"Failed to get key: {exc}")
            return
        if value is None:
            self._send_error(404, f"Key not found: {key}")
            return
        self._send_json({"key": key, "value": value})

    # ── Logging ──────────────────────────────────────────────────────────────

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Quiet default logging — only log at debug level if needed."""
        # Suppress per-request logging to keep CLI output clean.
        pass


def _get_encrypt_key() -> str | None:
    """Retrieve the encryption key from the environment or prompt the user."""
    key = os.environ.get(KEY_ENV_VAR)
    if key:
        return key
    try:
        import getpass
        return getpass.getpass("Decryption password: ")
    except (EOFError, KeyboardInterrupt):
        return None


def _get_api_key(cli_key: str | None = None) -> str | None:
    """Resolve the API authentication key.

    Priority: explicit CLI flag > ENVAULT_API_KEY env var > None (auth disabled).
    """
    if cli_key:
        return cli_key
    return os.environ.get(API_KEY_ENV_VAR) or None


def create_handler(
    store: SecretStore,
    config: EnvaultConfig,
    encrypt_key: str | None = None,
    api_key: str | None = None,
):
    """Return a BaseHTTPRequestHandler subclass bound to the given store/config.

    This avoids mutating the class-level attributes on SecretHandler directly,
    which could leak across instances in tests.
    """

    class _Handler(SecretHandler):
        pass

    _Handler.store = store  # type: ignore[attr-defined]
    _Handler.config = config  # type: ignore[attr-defined]
    _Handler.encrypt_key = encrypt_key  # type: ignore[attr-defined]
    _Handler.api_key = api_key  # type: ignore[attr-defined]
    return _Handler


def run_server(
    config: EnvaultConfig,
    port: int = 8080,
    host: str = "127.0.0.1",
    encrypt_key: str | None = None,
    store_name: str | None = None,
    api_key: str | None = None,
) -> None:
    """Start the HTTP server for the secrets API.

    Parameters
    ----------
    config : EnvaultConfig
        Loaded envault configuration.
    port : int
        Port to bind (default 8080).
    host : str
        Bind address (default "127.0.0.1" — localhost only for security).
    encrypt_key : str | None
        Encryption key; if *None* the key is read from ENVAULT_ENCRYPT_KEY or
        prompted interactively.
    store_name : str | None
        Named store from config to use; if *None* the default store is used.
    api_key : str | None
        Bearer token for API authentication. If provided, all /secrets
        endpoints require an Authorization: Bearer <api-key> header.
        If *None*, the ENVAULT_API_KEY env var is checked; if that is also
        unset, auth is disabled (with a warning).
    """

    # Resolve encryption key (same auth model as decrypt command)
    if encrypt_key is None:
        encrypt_key = _get_encrypt_key()
    if not encrypt_key:
        raise SystemExit("Error: encryption key required (set ENVAULT_ENCRYPT_KEY or provide --password)")

    # Resolve API key
    resolved_api_key = _get_api_key(api_key)

    # Build the store instance
    if store_name and store_name in config.stores:
        store_instance = get_store(config.stores[store_name])
    elif config.stores:
        # Use the first configured store
        first_name = next(iter(config.stores))
        store_instance = get_store(config.stores[first_name])
    else:
        store_instance = get_store("")

    handler_class = create_handler(store_instance, config, encrypt_key, resolved_api_key)
    server = HTTPServer((host, port), handler_class)

    from rich.console import Console
    console = Console()
    console.print(f"[green]✓[/green] envault serve listening on http://{host}:{port}")
    console.print(" GET /secrets — list all secret keys")
    console.print(" GET /secrets?prefix=X — filter keys by prefix")
    console.print(" GET /secrets/{key} — get decrypted value")
    console.print(" GET /health — store connectivity check")
    if resolved_api_key:
        console.print("[green]🔒[/green] API authentication enabled (Bearer token required)")
    else:
        console.print("[yellow]⚠[/yellow] No API key set — secrets endpoints are unauthenticated!")
        console.print("[dim]   Set --api-key flag or ENVAULT_API_KEY env var to enable auth[/dim]")

    console.print("[dim]Press Ctrl+C to stop[/dim]")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down…[/yellow]")
    finally:
        server.server_close()
