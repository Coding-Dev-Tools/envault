"""HTTP API server for exposing decrypted secrets as a JSON API.

Endpoints:
    GET /secrets           -> list all secret keys (or filter by prefix)
    GET /secrets/{key}     -> get decrypted value for a specific key
    GET /health            -> connectivity check for the backing store

Access control:
    Requests must provide an Authorization header matching the token passed to
    run_server(). This is intentionally simple because the surrounding CLI is
    meant for trusted developers, not untrusted network clients.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime, timezone
from envault.audit import AuditLogger
from envault.config import EnvaultConfig
from envault.encrypt import KEY_ENV_VAR
from envault.stores import LocalEnvStore, SecretStore, get_store
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _utc_now(tz: Any | None = None) -> str:
    if tz is None:
        return datetime.now(timezone.utc).isoformat()
    return datetime.now(tz).isoformat()


class SecretLogger:
    def __init__(self, audit_log_path: str) -> None:
        self._logger = AuditLogger(audit_log_path)

    def access(self, *, method: str, path: str, status: int, client: tuple[str, int] | None = None) -> None:
        try:
            client_string = ".".join([client[0] or "client", str(client[1])]) if client else "client"
            self._logger.log(
                action="http.access",
                key=path,
                env_file=".",
                source=client_string,
                details={
                    "method": method,
                    "path": path,
                    "status": status,
                    "timestamp_utc": _utc_now(),
                },
            )
        except Exception:
            pass

    def secret_access(self, path: str) -> None:
        with contextlib.suppress(Exception):
            self._logger.log(
                action="http.secret",
                key=path,
                env_file=".",
                source="SecretHandler",
                details={"timestamp_utc": _utc_now()},
            )


class SecretHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the envault secrets API."""

    # Set by create_handler() before the server starts.
    store: SecretStore
    config: EnvaultConfig
    encrypt_key: str | None
    logger: SecretLogger | None = None

    # ------------------------------------------------------------------
    # Auth / Audit
    # ------------------------------------------------------------------

    def _require_auth(self) -> bool:
        token = self._request_token()
        expected = getattr(self, "encrypt_key", None)
        if token and expected and token == expected:
            return True
        self._send_json({"error": "Unauthorized"}, status=401)
        return False

    def _request_token(self) -> str | None:
        auth = getattr(self, "headers", {}).get("Authorization", "")
        if isinstance(auth, str) and auth.startswith("Bearer "):
            candidate = auth[7:]
            if candidate:
                return candidate
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if self.logger is not None:
            self.logger.access(method=self.command, path=self.path, status=status, client=self.client_address)

    def _masked_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            return "Request failed"
        # Mask any measurement strings like "-n N" or "12345" in the message
        return "Request failed"

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 – stdlib naming convention
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if not self._require_auth():
            return
        if self.logger is not None:
            self.logger.secret_access(path)
        if path == "/health":
            self._handle_health()
        elif path == "/secrets":
            self._handle_secrets_list(query)
        elif path.startswith("/secrets/"):
            key = path[len("/secrets/") :]
            self._handle_secrets_get(key)
        else:
            self._send_json({"error": "Not found"}, status=404)

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def _handle_health(self) -> None:
        store = self.store
        checks: dict[str, Any] = {}
        if isinstance(store, LocalEnvStore):
            env_file = Path(store.env_file)
            checks["local"] = {"status": "ok" if env_file.exists() else "error", "path": str(env_file)}
        else:
            store_type = type(store).__name__
            try:
                store.list_keys()
                checks[store_type] = {"status": "ok"}
            except Exception as exc:
                checks[store_type] = {"status": "error", "detail": self._masked_message(exc)}
        overall = "ok" if all(check.get("status") == "ok" for check in checks.values()) else "error"
        self._send_json({"status": overall, "checks": checks})

    def _handle_secrets_list(self, query: dict[str, list[str]]) -> None:
        prefix = query.get("prefix", [""])[0]
        try:
            keys = self.store.list_keys(prefix=prefix)
        except Exception as exc:
            self._send_json({"error": f"Failed to list keys: {self._masked_message(exc)}"}, status=500)
            return
        self._send_json({"keys": keys, "count": len(keys)})

    def _handle_secrets_get(self, key: str) -> None:
        if not key:
            self._send_json({"error": "Key is required"}, status=400)
            return
        try:
            value = self.store.get(key)
        except Exception as exc:
            self._send_json({"error": f"Failed to get key: {self._masked_message(exc)}"}, status=500)
            return
        if value is None:
            self._send_json({"error": f"Key not found: {key}"}, status=404)
            return
        self._send_json({"key": key, "value": value})

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


# ------------------------------------------------------------------
# Server bootstrap
# ------------------------------------------------------------------

def _get_encrypt_key() -> str | None:
    key = os.environ.get(KEY_ENV_VAR)
    if key:
        return key
    try:
        import getpass

        return getpass.getpass("Decryption password: ")
    except (EOFError, KeyboardInterrupt):
        return None


def create_handler(store: SecretStore, config: EnvaultConfig, encrypt_key: str | None = None):
    class _Handler(SecretHandler):
        pass

    _Handler.store = store  # type: ignore[attr-defined]
    _Handler.config = config  # type: ignore[attr-defined]
    _Handler.encrypt_key = encrypt_key  # type: ignore[attr-defined]
    _Handler.logger = None  # type: ignore[attr-defined]
    return _Handler


def run_server(
    config: EnvaultConfig,
    port: int = 8080,
    host: str = "0.0.0.0",
    encrypt_key: str | None = None,
    store_name: str | None = None,
) -> None:
    if encrypt_key is None:
        encrypt_key = _get_encrypt_key()
    if not encrypt_key:
        raise SystemExit("Error: encryption key required (set ENVAULT_ENCRYPT_KEY or provide --password)")
    if store_name and store_name in config.stores:
        store_instance = get_store(config.stores[store_name])
    elif config.stores:
        first_name = next(iter(config.stores))
        store_instance = get_store(config.stores[first_name])
    else:
        store_instance = get_store("")
    handler_class = create_handler(store_instance, config, encrypt_key)
    if not hasattr(handler_class, "logger") or handler_class.logger is None:
        handler_class.logger = SecretLogger(getattr(config, "audit_log_path", ".envault-audit.log"))
    server = HTTPServer((host, port), handler_class)
    from rich.console import Console

    console = Console()
    console.print(f"[green]\u2713[/green] envault serve listening on http://{host}:{port}")
    console.print("  GET /secrets           - list all secret keys")
    console.print("  GET /secrets?prefix=X  - filter keys by prefix")
    console.print("  GET /secrets/{key}     - get decrypted value")
    console.print("  GET /health            - store connectivity check")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    finally:
        server.server_close()
