"""HTTP API server for exposing decrypted secrets as a JSON API.

Endpoints:
 GET /secrets -> list all secret keys (or filter by ?prefix=FOO)
 GET /secrets/{key} -> get decrypted value for a specific key
 GET /health -> connectivity check for the backing store
 GET /auth/info -> show configured auth methods and identity
"""

from __future__ import annotations

import json
import os
from envault.auth import BearerAuth, MultiAuth, ApiKeyAuth, OAuth2Auth, build_auth_from_env
from envault.config import EnvaultConfig
from envault.encrypt import KEY_ENV_VAR
from envault.stores import LocalEnvStore, SecretStore, get_store
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


class SecretHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the envault secrets API."""

    # Set by run_server() before the server starts
    store: SecretStore
    config: EnvaultConfig
    encrypt_key: str | None
    api_token: str | None

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

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _check_auth(self) -> bool:
        """Verify Bearer token if api_token is configured.

        Returns True if the request is authenticated (or auth is disabled).
        Sends a 401 and returns False if authentication fails.
        """
        if not self.api_token:
            # No token configured — auth not required
            return True

        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self._send_error(401, "Unauthorized: Bearer token required")
            return False

        token = auth_header[len("Bearer "):]
        if token != self.api_token:
            self._send_error(403, "Forbidden: invalid token")
            return False

        return True

    # ── Routing ──────────────────────────────────────────────────────────────

    def do_GET(self) -> None: # noqa: N802 – stdlib naming convention
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        # Health endpoint is always accessible (useful for load balancers)
        if path == "/health":
            self._handle_health()
            return

        # All other endpoints require auth
        if not self._check_auth():
            return

        if path == "/secrets":
            self._handle_secrets_list(query)
        elif path.startswith("/secrets/"):
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


def create_handler(store: SecretStore, config: EnvaultConfig, encrypt_key: str | None = None, api_token: str | None = None):
    """Return a BaseHTTPRequestHandler subclass bound to the given store/config.

    This avoids mutating the class-level attributes on SecretHandler directly,
    which could leak across instances in tests.
    """

    class _Handler(SecretHandler):
        pass

    _Handler.store = store # type: ignore[attr-defined]
    _Handler.config = config # type: ignore[attr-defined]
    _Handler.encrypt_key = encrypt_key # type: ignore[attr-defined]
    _Handler.api_token = api_token # type: ignore[attr-defined]
    return _Handler


def run_server(
    config: EnvaultConfig,
    port: int = 8080,
    host: str = "127.0.0.1",
    encrypt_key: str | None = None,
    store_name: str | None = None,
    api_token: str | None = None,
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
    api_token : str | None
        Bearer token for API authentication. If *None*, reads from
        ENVAULT_API_TOKEN env var. If still unset, API auth is disabled
        with a warning (only safe on localhost).
    """

    # Resolve encryption key (same auth model as decrypt command)
    if encrypt_key is None:
        encrypt_key = _get_encrypt_key()
    if not encrypt_key:
        raise SystemExit("Error: encryption key required (set ENVAULT_ENCRYPT_KEY or provide --password)")

    # Resolve API token for Bearer auth
    if api_token is None:
        api_token = os.environ.get("ENVAULT_API_TOKEN")
    if not api_token and host not in ("127.0.0.1", "localhost"):
        raise SystemExit(
            "Error: API token required when binding to non-localhost address. "
            "Set ENVAULT_API_TOKEN or pass --api-token."
        )

    # Build the store instance
    if store_name and store_name in config.stores:
        store_instance = get_store(config.stores[store_name])
    elif config.stores:
        # Use the first configured store
        first_name = next(iter(config.stores))
        store_instance = get_store(config.stores[first_name])
    else:
        store_instance = get_store("")

    handler_class = create_handler(store_instance, config, encrypt_key, api_token=api_token)
    server = HTTPServer((host, port), handler_class)

    from rich.console import Console
    console = Console()
    console.print(f"[green]✓[/green] envault serve listening on http://{host}:{port}")
    console.print(" GET /secrets — list all secret keys")
    console.print(" GET /secrets?prefix=X — filter keys by prefix")
    console.print(" GET /secrets/{key} — get decrypted value")
    console.print(" GET /health — store connectivity check")
    if api_token:
        console.print("[green]🔒[/green] API authentication enabled (Bearer token)")
    else:
        console.print("[yellow]⚠[/yellow] No API token set — secrets accessible without auth (localhost only)")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down…[/yellow]")
    finally:
        server.server_close()
