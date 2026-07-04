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

import base64
import json
import os
import secrets as _secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from envault.config import EnvaultConfig
from envault.encrypt import KEY_ENV_VAR
from envault.stores import LocalEnvStore, SecretStore, get_store

# Environment variable for API authentication key
API_KEY_ENV_VAR = "ENVAULT_API_KEY"  # pragma: allowlist secret

_OAUTH2_CACHE_TTL: float = 300.0  # seconds
_oauth2_cache: dict[str, tuple[bool, float]] = {}


class SecretHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the envault secrets API."""

    # Set by create_handler() before the server starts
    store: SecretStore
    config: EnvaultConfig
    encrypt_key: str | None = None
    api_key: str | None = None
    api_token: str | None = None
    oauth_introspect_url: str | None = None
    oauth_userinfo_url: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    auth_mode: str = "any"

    # -- Helpers ---------------------------------------------------------------

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
        if not auth_header:
            self._send_error(401, "Unauthorized: valid Bearer token required")
            return False

        token = auth_header[len("Bearer ") :] if auth_header.startswith("Bearer ") else auth_header
        if not token or not token.strip():
            self._send_error(401, "Unauthorized: valid Bearer token required")
            return False

        if (
            _secrets.compare_digest(token.strip(), self.api_key)
            if self.api_key
            else _secrets.compare_digest(token.strip(), "")
        ):
            return True

        self._send_error(401, "Unauthorized: valid Bearer token required")
        return False

    # ── Routing ──────────────────────────────────────────────────────────────

    def _check_bearer_token(self) -> bool:
        """Check Bearer token -- static or OAuth2 introspection/userinfo.

        Returns True if authenticated.
        Returns False if auth failed (error already sent).
        """
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self._send_error(401, "Unauthorized: Bearer token required")
            return False

        token = auth_header[len("Bearer ") :]

        # If OAuth2 introspection URL is configured, validate via introspection
        if self.oauth_introspect_url:
            return self._oauth2_introspect(token)

        # If OAuth2 userinfo URL is configured, validate via userinfo
        if self.oauth_userinfo_url:
            return self._oauth2_userinfo(token)

        # Otherwise, fall back to static token check
        if token != (self.api_token or ""):
            self._send_error(401, "Unauthorized: invalid Bearer token")
            return False

        return True

    def _oauth2_introspect(self, token: str) -> bool:
        """Validate a Bearer token via OAuth2 token introspection (RFC 7662).

        POSTs to the configured introspection endpoint with the token.
        Returns True if the endpoint returns ``{"active": true}``.
        Returns False and sends a 401/403 on failure.
        Results are cached for _OAUTH2_CACHE_TTL seconds.
        """
        # Check cache
        cached = _oauth2_cache.get(token)
        if cached is not None:
            is_active, expires_at = cached
            if time.monotonic() < expires_at:
                if is_active:
                    return True
                self._send_error(401, "Unauthorized: token is not active")
                return False
            del _oauth2_cache[token]

        # Build headers -- include Basic auth if client credentials are configured
        introspect_headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self.oauth_client_id and self.oauth_client_secret:
            credentials = f"{self.oauth_client_id}:{self.oauth_client_secret}"
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
            introspect_headers["Authorization"] = f"Basic {encoded}"

        try:
            # Try using requests if available (better error handling / timeouts)
            import requests  # type: ignore[import-untyped]

            resp = requests.post(
                self.oauth_introspect_url,
                data={"token": token},
                headers=introspect_headers,
                timeout=5,
            )
            if resp.status_code != 200:
                _oauth2_cache[token] = (False, time.monotonic() + 60)
                self._send_error(401, "Unauthorized: token introspection failed")
                return False
            result = resp.json()
        except ImportError:
            # Fallback to stdlib urllib
            try:
                body = urlencode({"token": token}).encode("utf-8")
                req = Request(
                    self.oauth_introspect_url,
                    data=body,
                    headers=introspect_headers,
                    method="POST",
                )
                with urlopen(req, timeout=5) as resp:  # noqa: S310
                    if resp.status != 200:
                        _oauth2_cache[token] = (False, time.monotonic() + 60)
                        self._send_error(401, "Unauthorized: token introspection failed")
                        return False
                    result = json.loads(resp.read().decode("utf-8"))
            except (URLError, OSError, json.JSONDecodeError) as exc:
                self._send_error(502, f"Token introspection error: {exc}")
                return False
            except Exception as exc:
                self._send_error(502, f"Token introspection error: {exc}")
                return False

        if not result.get("active", False):
            _oauth2_cache[token] = (False, time.monotonic() + 60)
            self._send_error(401, "Unauthorized: token is not active")
            return False

        # Cache successful result
        _oauth2_cache[token] = (True, time.monotonic() + _OAUTH2_CACHE_TTL)
        return True

    def _oauth2_userinfo(self, token: str) -> bool:
        """Validate a Bearer token via OAuth2 userinfo endpoint (OIDC).

        GETs the userinfo endpoint with the Bearer token.
        Returns True if the endpoint returns 200 with user info.
        Returns False and sends a 401 on failure.
        Results are cached for _OAUTH2_CACHE_TTL seconds.
        """
        # Check cache
        cached = _oauth2_cache.get(token)
        if cached is not None:
            is_active, expires_at = cached
            if time.monotonic() < expires_at:
                if is_active:
                    return True
                self._send_error(401, "Unauthorized: token rejected by provider")
                return False
            del _oauth2_cache[token]

        try:
            # Try using requests if available
            import requests  # type: ignore[import-untyped]

            resp = requests.get(
                self.oauth_userinfo_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if resp.status_code != 200:
                _oauth2_cache[token] = (False, time.monotonic() + 60)
                self._send_error(401, "Unauthorized: token rejected by provider")
                return False
        except ImportError:
            # Fallback to stdlib urllib
            try:
                req = Request(
                    self.oauth_userinfo_url,
                    headers={"Authorization": f"Bearer {token}"},
                    method="GET",
                )
                with urlopen(req, timeout=5) as resp:  # noqa: S310
                    if resp.status != 200:
                        _oauth2_cache[token] = (False, time.monotonic() + 60)
                        self._send_error(401, "Unauthorized: token rejected by provider")
                        return False
            except (URLError, OSError) as exc:
                self._send_error(502, f"OAuth2 userinfo error: {exc}")
                return False
            except Exception as exc:
                self._send_error(502, f"OAuth2 userinfo error: {exc}")
                return False

        # Cache successful result
        _oauth2_cache[token] = (True, time.monotonic() + _OAUTH2_CACHE_TTL)
        return True

    def _check_auth(self) -> bool:
        """Verify authentication based on the configured auth mode.

        Auth modes:
        - "bearer": Bearer token only (static or OAuth2 introspection/userinfo)
        - "api-key": X-API-Key header only
        - "oauth2": Bearer token validated via OAuth2 introspection or userinfo
        - "any": Try X-API-Key first, then Bearer token

        Returns True if the request is authenticated (or auth is disabled).
        Sends a 401/403 and returns False if authentication fails.
        """
        # If no auth credentials are configured at all, skip auth
        has_any_auth = self.api_token or self.api_key or self.oauth_introspect_url or self.oauth_userinfo_url
        if not has_any_auth:
            return True

        mode = self.auth_mode

        if mode == "api-key":
            # Only X-API-Key is accepted
            if not self.api_key:
                self._send_error(
                    401,
                    "Unauthorized: X-API-Key header required (no API key configured)",
                )
                return False
            api_key_header = self.headers.get("X-API-Key", "")
            if not api_key_header:
                self._send_error(401, "Unauthorized: X-API-Key header required")
                return False
            if api_key_header != self.api_key:
                self._send_error(401, "Unauthorized: invalid API key")
                return False
            return True

        if mode == "oauth2":
            # Bearer token required, validated via OAuth2
            if not self.oauth_introspect_url and not self.oauth_userinfo_url:
                self._send_error(401, "Unauthorized: OAuth2 endpoint not configured")
                return False
            return self._check_bearer_token()

        if mode == "any":
            # Try X-API-Key first, then Bearer
            api_key_header = self.headers.get("X-API-Key", "")
            if api_key_header and self.api_key:
                if api_key_header == self.api_key:
                    return True
                # API key was provided but wrong -- return error immediately
                self._send_error(401, "Unauthorized: invalid API key")
                return False

            # Fall through to Bearer token check
            return self._check_bearer_token()

        # Default: "bearer" mode
        return self._check_bearer_token()

    # -- Routing ---------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 -- stdlib naming convention
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        # Health endpoint is always accessible (useful for load balancers)
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
            key = path[len("/secrets/") :]
            self._handle_secrets_get(key)
        else:
            self._send_error(404, "Not found")

    # -- Endpoints -------------------------------------------------------------

    def _handle_health(self) -> None:
        """GET /health -- connectivity check for the backing store."""
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

    def _handle_auth_info(self) -> None:
        """GET /auth/info -- show configured auth methods (no secrets exposed).

        This endpoint is always accessible (like /health) so clients can
        discover what auth methods the server accepts before making
        authenticated requests.
        """
        methods: list[str] = []
        if self.api_token:
            methods.append("bearer")
        if self.api_key:
            methods.append("api-key")
        if self.oauth_introspect_url:
            methods.append("oauth2-introspect")
        if self.oauth_userinfo_url:
            methods.append("oauth2-userinfo")

        self._send_json(
            {
                "auth_mode": self.auth_mode,
                "methods": methods,
                "requires_auth": bool(
                    self.api_token or self.api_key or self.oauth_introspect_url or self.oauth_userinfo_url
                ),
            }
        )

    def _handle_secrets_list(self, query: dict[str, list[str]]) -> None:
        """GET /secrets -- list keys, optionally filtered by ?prefix=."""
        prefix = query.get("prefix", [""])[0]
        try:
            keys = self.store.list_keys(prefix=prefix)
        except Exception as exc:
            self._send_error(500, f"Failed to list keys: {exc}")
            return
        self._send_json({"keys": keys, "count": len(keys)})

    def _handle_secrets_get(self, key: str) -> None:
        """GET /secrets/{key} -- get decrypted value for a single key."""
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

    # -- Logging ---------------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Quiet default logging -- only log at debug level if needed."""
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
    api_token: str | None = None,
    oauth_introspect_url: str | None = None,
    oauth_userinfo_url: str | None = None,
    oauth_client_id: str | None = None,
    oauth_client_secret: str | None = None,
    auth_mode: str = "any",
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
    _Handler.api_token = api_token  # type: ignore[attr-defined]
    _Handler.oauth_introspect_url = oauth_introspect_url  # type: ignore[attr-defined]
    _Handler.oauth_userinfo_url = oauth_userinfo_url  # type: ignore[attr-defined]
    _Handler.oauth_client_id = oauth_client_id  # type: ignore[attr-defined]
    _Handler.oauth_client_secret = oauth_client_secret  # type: ignore[attr-defined]
    _Handler.auth_mode = auth_mode  # type: ignore[attr-defined]
    return _Handler


def run_server(
    config: EnvaultConfig,
    port: int = 8080,
    host: str = "127.0.0.1",
    encrypt_key: str | None = None,
    store_name: str | None = None,
    api_key: str | None = None,
    api_token: str | None = None,
    oauth_introspect_url: str | None = None,
    oauth_userinfo_url: str | None = None,
    oauth_client_id: str | None = None,
    oauth_client_secret: str | None = None,
    auth_mode: str = "any",
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

    # Resolve API token for Bearer auth
    if api_token is None:
        api_token = os.environ.get("ENVAULT_API_TOKEN")

    # Resolve API key for X-API-Key auth
    if api_key is None:
        api_key = os.environ.get("ENVAULT_API_KEY")

    # Resolve OAuth2 introspection URL
    if oauth_introspect_url is None:
        oauth_introspect_url = os.environ.get("ENVAULT_OAUTH_INTROSPECT_URL")

    # Resolve OAuth2 userinfo URL
    if oauth_userinfo_url is None:
        oauth_userinfo_url = os.environ.get("ENVAULT_OAUTH_USERINFO_URL")

    # Resolve OAuth2 client credentials (for authenticated introspection)
    if oauth_client_id is None:
        oauth_client_id = os.environ.get("ENVAULT_OAUTH_CLIENT_ID")

    if oauth_client_secret is None:
        oauth_client_secret = os.environ.get("ENVAULT_OAUTH_CLIENT_SECRET")

    # Validate auth_mode
    valid_modes = ("bearer", "api-key", "oauth2", "any")
    if auth_mode not in valid_modes:
        raise SystemExit(f"Error: invalid auth mode '{auth_mode}'. Choose from: {', '.join(valid_modes)}")

    # For oauth2 mode, at least one OAuth2 endpoint is required
    if auth_mode == "oauth2" and not oauth_introspect_url and not oauth_userinfo_url:
        raise SystemExit(
            "Error: OAuth2 endpoint required for 'oauth2' auth mode. "
            "Set ENVAULT_OAUTH_INTROSPECT_URL or ENVAULT_OAUTH_USERINFO_URL."
        )

    # Safety check: require some auth on non-localhost
    has_any_auth = api_token or api_key or oauth_introspect_url or oauth_userinfo_url
    if not has_any_auth and host not in ("127.0.0.1", "localhost"):
        raise SystemExit(
            "Error: API authentication required when binding to non-localhost address. "
            "Set ENVAULT_API_TOKEN, ENVAULT_API_KEY, or ENVAULT_OAUTH_INTROSPECT_URL."
        )

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
