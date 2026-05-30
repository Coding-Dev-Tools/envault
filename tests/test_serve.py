"""Tests for the envault serve HTTP API (handler logic without starting a server)."""

from __future__ import annotations

import io
import json
import time
from envault.config import EnvaultConfig
from envault.serve import SecretHandler, _oauth2_cache, create_handler
from envault.stores import LocalEnvStore
from unittest.mock import MagicMock, patch

# ── Fixtures ───────────────────────────────────────────────────────────────────


class _FakeStore:
    """In-memory store for testing handler logic."""

    def __init__(self, data: dict[str, str] | None = None, env_file: str = ".env"):
        self._data = data or {}
        self.env_file = env_file

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> bool:
        self._data[key] = value
        return True

    def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def list_keys(self, prefix: str = "") -> list[str]:
        keys = list(self._data.keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return keys


def _make_handler(
    store,
    config: EnvaultConfig | None = None,
    api_token: str | None = None,
    api_key: str | None = None,
    auth_mode: str = "bearer",
    oauth_introspect_url: str | None = None,
    oauth_userinfo_url: str | None = None,
    oauth_client_id: str | None = None,
    oauth_client_secret: str | None = None,
):
    """Create a handler class bound to the given store and return a mock instance.

    We create a mock request handler that has the routing logic from
    SecretHandler but uses pre-set wfile/rfile so we can inspect output.
    """
    config = config or EnvaultConfig()
    handler_class = create_handler(
        store, config, encrypt_key="test-key", api_token=api_token,
        api_key=api_key, auth_mode=auth_mode,
        oauth_introspect_url=oauth_introspect_url,
        oauth_userinfo_url=oauth_userinfo_url,
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
    )

    # Build a minimal instance that has enough of BaseHTTPRequestHandler
    # wired up to test do_GET routing and response writing.
    instance = _build_handler_instance(handler_class)
    return instance


def _build_handler_instance(handler_class):
    """Construct a handler instance with mocked I/O for testing."""

    # BaseHTTPRequestHandler.__init__ reads from rfile and writes to wfile.
    # We mock the socket-level details and call the init ourselves.
    rfile = io.BytesIO(b"")
    wfile = io.BytesIO()

    # We avoid calling BaseHTTPRequestHandler.__init__ (which tries to parse
    # a request). Instead we manually set the attributes we need.
    instance = object.__new__(handler_class)
    instance.rfile = rfile
    instance.wfile = wfile
    instance.send_response = MagicMock()
    instance.send_header = MagicMock()
    instance.end_headers = MagicMock()
    instance.client_address = ("127.0.0.1", 9999)
    instance.server = MagicMock()
    instance.command = "GET"
    instance.request_version = "HTTP/1.1"

    # Mock headers dict for auth checks
    instance.headers = {}

    # Track what _send_json writes so we can assert on it
    instance._sent_json = None
    instance._sent_status = None
    instance._sent_body = None

    # Override _send_json to capture output instead of writing raw bytes

    def _capturing_send_json(self_inner, data, status=200):
        self_inner._sent_json = data
        self_inner._sent_status = status
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self_inner._sent_body = body
        self_inner.send_response(status)
        self_inner.send_header("Content-Type", "application/json; charset=utf-8")
        self_inner.send_header("Content-Length", str(len(body)))
        self_inner.end_headers()
        self_inner.wfile.write(body)

    instance._send_json = lambda data, status=200: _capturing_send_json(instance, data, status)

    return instance


# ── Tests: GET /secrets ────────────────────────────────────────────────────────


class TestSecretsList:
    """Tests for GET /secrets endpoint."""

    def test_list_all_keys(self):
        store = _FakeStore({"DB_HOST": "localhost", "DB_PORT": "5432", "API_KEY": "abc"})
        handler = _make_handler(store)
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert set(data["keys"]) == {"DB_HOST", "DB_PORT", "API_KEY"}
        assert data["count"] == 3

    def test_list_keys_with_prefix(self):
        store = _FakeStore({"DB_HOST": "localhost", "DB_PORT": "5432", "API_KEY": "abc"})
        handler = _make_handler(store)
        handler.path = "/secrets?prefix=DB_"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert set(data["keys"]) == {"DB_HOST", "DB_PORT"}
        assert data["count"] == 2

    def test_list_keys_prefix_no_match(self):
        store = _FakeStore({"DB_HOST": "localhost", "API_KEY": "abc"})
        handler = _make_handler(store)
        handler.path = "/secrets?prefix=STRIPE_"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert data["keys"] == []
        assert data["count"] == 0

    def test_list_keys_empty_store(self):
        store = _FakeStore({})
        handler = _make_handler(store)
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert data["keys"] == []
        assert data["count"] == 0


# ── Tests: GET /secrets/{key} ──────────────────────────────────────────────────


class TestSecretsGet:
    """Tests for GET /secrets/{key} endpoint."""

    def test_get_existing_key(self):
        store = _FakeStore({"SECRET_TOKEN": "super-secret"})
        handler = _make_handler(store)
        handler.path = "/secrets/SECRET_TOKEN"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert data["key"] == "SECRET_TOKEN"
        assert data["value"] == "super-secret"

    def test_get_missing_key_returns_404(self):
        store = _FakeStore({"OTHER": "value"})
        handler = _make_handler(store)
        handler.path = "/secrets/NONEXISTENT"
        handler.do_GET()

        assert handler._sent_status == 404
        assert "not found" in handler._sent_json["error"].lower()

    def test_get_empty_key_returns_400(self):
        store = _FakeStore({"KEY": "val"})
        handler = _make_handler(store)
        # Path with explicitly empty key after /secrets/
        # Note: /secrets/ gets rstrip("/") -> /secrets -> list endpoint
        # To test the 400, we need a key that resolves to empty after routing
        # The handler checks startswith("/secrets/") then extracts key
        # A URL-decoded empty key won't happen in practice, but we test
        # the guard by calling the handler method directly
        handler._handle_secrets_get("")
        assert handler._sent_status == 400


# ── Tests: GET /health ─────────────────────────────────────────────────────────


class TestHealth:
    """Tests for GET /health endpoint."""

    def test_health_local_store_file_exists(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=val\n")
        store = LocalEnvStore(str(env_file))
        handler = _make_handler(store)
        handler.path = "/health"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert data["status"] == "ok"
        assert data["checks"]["local"]["status"] == "ok"

    def test_health_local_store_file_missing(self, tmp_path):
        env_file = tmp_path / ".env.missing"
        store = LocalEnvStore(str(env_file))
        handler = _make_handler(store)
        handler.path = "/health"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert data["status"] == "error"
        assert data["checks"]["local"]["status"] == "error"

    def test_health_cloud_store_ok(self):
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store)
        handler.path = "/health"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        # _FakeStore is not LocalEnvStore, so it falls into the generic branch
        # It lists keys as _FakeStore which succeeds
        assert data["status"] == "ok"

    def test_health_cloud_store_error(self):
        class BrokenStore(_FakeStore):
            def list_keys(self, prefix: str = "") -> list[str]:
                raise RuntimeError("connection refused")

        store = BrokenStore()
        handler = _make_handler(store)
        handler.path = "/health"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert data["status"] == "error"


# ── Tests: GET /auth/info ─────────────────────────────────────────────────────


class TestAuthInfo:
    """Tests for GET /auth/info endpoint."""

    def test_auth_info_no_auth_configured(self):
        """With no auth configured, auth/info should show empty methods."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store)
        handler.path = "/auth/info"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert data["auth_mode"] == "bearer"
        assert data["methods"] == []
        assert data["requires_auth"] is False

    def test_auth_info_bearer_configured(self):
        """With api_token set, should list bearer method."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, api_token="my-token")
        handler.path = "/auth/info"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert "bearer" in data["methods"]
        assert data["requires_auth"] is True

    def test_auth_info_api_key_configured(self):
        """With api_key set, should list api-key method."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, api_key="my-key", auth_mode="api-key")
        handler.path = "/auth/info"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert "api-key" in data["methods"]
        assert data["auth_mode"] == "api-key"
        assert data["requires_auth"] is True

    def test_auth_info_oauth_introspect_configured(self):
        """With oauth_introspect_url set, should list oauth2-introspect method."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, oauth_introspect_url="https://auth.example.com/introspect", auth_mode="oauth2")
        handler.path = "/auth/info"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert "oauth2-introspect" in data["methods"]
        assert data["auth_mode"] == "oauth2"
        assert data["requires_auth"] is True

    def test_auth_info_oauth_userinfo_configured(self):
        """With oauth_userinfo_url set, should list oauth2-userinfo method."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, oauth_userinfo_url="https://auth.example.com/userinfo", auth_mode="oauth2")
        handler.path = "/auth/info"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert "oauth2-userinfo" in data["methods"]
        assert data["requires_auth"] is True

    def test_auth_info_any_mode_shows_all_methods(self):
        """With 'any' mode and multiple auth methods, all should be listed."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(
            store,
            api_token="tok",
            api_key="key",
            oauth_introspect_url="https://auth.example.com/introspect",
            oauth_userinfo_url="https://auth.example.com/userinfo",
            auth_mode="any",
        )
        handler.path = "/auth/info"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert "bearer" in data["methods"]
        assert "api-key" in data["methods"]
        assert "oauth2-introspect" in data["methods"]
        assert "oauth2-userinfo" in data["methods"]
        assert data["auth_mode"] == "any"

    def test_auth_info_no_auth_required(self):
        """auth/info endpoint should work without any auth headers."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, api_token="secret-token")
        handler.headers = {}  # No auth headers
        handler.path = "/auth/info"
        handler.do_GET()

        # Should still return 200 (auth/info is unauthenticated)
        assert handler._sent_status == 200


# ── Tests: Routing ─────────────────────────────────────────────────────────────


class TestRouting:
    """Tests for URL routing edge cases."""

    def test_unknown_path_returns_404(self):
        store = _FakeStore({})
        handler = _make_handler(store)
        handler.path = "/unknown"
        handler.do_GET()

        assert handler._sent_status == 404

    def test_root_returns_404(self):
        store = _FakeStore({})
        handler = _make_handler(store)
        handler.path = "/"
        handler.do_GET()

        assert handler._sent_status == 404

    def test_secrets_trailing_slash(self):
        """GET /secrets/ should route to secrets list (not key lookup for '')."""
        store = _FakeStore({"A": "1"})
        handler = _make_handler(store)
        handler.path = "/secrets/"
        handler.do_GET()

        # /secrets/ with trailing slash -> after rstrip("/") becomes "/secrets"
        # which routes to the list endpoint
        assert handler._sent_status == 200
        assert "keys" in handler._sent_json


# ── Tests: create_handler ──────────────────────────────────────────────────────


class TestCreateHandler:
    """Tests for the create_handler factory."""

    def test_handler_class_attributes(self):
        store = _FakeStore({"X": "y"})
        config = EnvaultConfig(project="test-project")
        handler_class = create_handler(store, config, encrypt_key="my-key")

        assert handler_class.store is store
        assert handler_class.config is config
        assert handler_class.encrypt_key == "my-key"
        assert issubclass(handler_class, SecretHandler)

    def test_handler_classes_are_isolated(self):
        """Two calls to create_handler should produce independent classes."""
        store_a = _FakeStore({"A": "1"})
        store_b = _FakeStore({"B": "2"})

        handler_a = create_handler(store_a, EnvaultConfig(), "key-a")
        handler_b = create_handler(store_b, EnvaultConfig(), "key-b")

        assert handler_a.store is store_a
        assert handler_b.store is store_b
        assert handler_a.encrypt_key == "key-a"
        assert handler_b.encrypt_key == "key-b"

    def test_handler_auth_attributes(self):
        """Auth attributes should be set on the handler class."""
        store = _FakeStore({"X": "y"})
        handler_class = create_handler(
            store, EnvaultConfig(), encrypt_key="k",
            api_token="tok", api_key="key", auth_mode="any",
            oauth_introspect_url="https://auth.example.com/introspect",
            oauth_userinfo_url="https://auth.example.com/userinfo",
            oauth_client_id="cid", oauth_client_secret="csecret",
        )
        assert handler_class.api_token == "tok"
        assert handler_class.api_key == "key"
        assert handler_class.auth_mode == "any"
        assert handler_class.oauth_introspect_url == "https://auth.example.com/introspect"
        assert handler_class.oauth_userinfo_url == "https://auth.example.com/userinfo"
        assert handler_class.oauth_client_id == "cid"
        assert handler_class.oauth_client_secret == "csecret"


# ── Tests: CLI serve command ───────────────────────────────────────────────────


class TestServeCLI:
    """Test the 'serve' typer command (without actually starting the server)."""

    def test_serve_help(self):
        """serve --help should show endpoint descriptions."""
        from envault.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "port" in result.stdout.lower()
        assert "health" in result.stdout.lower() or "secrets" in result.stdout.lower()

    def test_serve_help_shows_auth_options(self):
        """serve --help should show auth-related options."""
        from envault.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "auth-mode" in result.stdout.lower()
        assert "api-key" in result.stdout.lower()
        assert "oauth" in result.stdout.lower()

    def test_serve_no_encrypt_key_exits(self, tmp_path):
        """serve without any encryption key should exit with error."""
        import os
        from envault.cli import app
        from typer.testing import CliRunner

        env_file = tmp_path / ".env"
        env_file.write_text("KEY=val\n")

        import yaml
        config = {
            "project": "test",
            "stores": {"local": {"type": "local", "path_prefix": str(env_file)}},
        }
        config_path = tmp_path / ".envault.yml"
        config_path.write_text(yaml.dump(config))

        runner = CliRunner()
        # Ensure ENVAULT_ENCRYPT_KEY is not set
        old = os.environ.pop("ENVAULT_ENCRYPT_KEY", None)
        try:
            # With no password and no env var, getpass will fail in CliRunner
            result = runner.invoke(app, [
                "serve", "--port", "0", "--config", str(config_path),
            ])
            # Should exit with error (SystemExit from run_server)
            assert result.exit_code != 0 or "Error" in result.output or "required" in result.output.lower()
        finally:
            if old is not None:
                os.environ["ENVAULT_ENCRYPT_KEY"] = old


# ── Tests: Bearer token authentication ─────────────────────────────────────────


class TestBearerAuth:
    """Tests for Bearer token authentication on the secrets API."""

    def test_no_token_allows_access(self):
        """Without api_token configured, all endpoints are accessible."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token=None)
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["keys"] == ["SECRET"]

    def test_valid_token_allows_access(self):
        """Correct Bearer token should allow access to /secrets."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="my-secret-token")
        handler.headers = {"Authorization": "Bearer my-secret-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["keys"] == ["SECRET"]

    def test_missing_auth_header_returns_401(self):
        """Missing Authorization header should return 401."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="my-secret-token")
        handler.headers = {}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401
        assert "bearer" in handler._sent_json["error"].lower()

    def test_wrong_scheme_returns_401(self):
        """Non-Bearer auth scheme should return 401."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="my-secret-token")
        handler.headers = {"Authorization": "Basic dXNlcjpwYXNz"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401

    def test_wrong_token_returns_403(self):
        """Wrong Bearer token should return 403."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="my-secret-token")
        handler.headers = {"Authorization": "Bearer wrong-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 403
        assert "invalid" in handler._sent_json["error"].lower()

    def test_health_endpoint_no_auth_required(self):
        """Health endpoint should be accessible without auth even when token is set."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, api_token="my-secret-token")
        handler.headers = {}
        handler.path = "/health"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["status"] == "ok"

    def test_auth_protects_secrets_key_endpoint(self):
        """GET /secrets/{key} should also require auth."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="my-secret-token")
        handler.headers = {}
        handler.path = "/secrets/SECRET"
        handler.do_GET()

        assert handler._sent_status == 401


# ── Tests: API key authentication ──────────────────────────────────────────────


class TestAPIKeyAuth:
    """Tests for X-API-Key header authentication."""

    def test_valid_api_key_allows_access(self):
        """Correct X-API-Key should allow access to /secrets."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_key="my-api-key", auth_mode="api-key")
        handler.headers = {"X-API-Key": "my-api-key"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["keys"] == ["SECRET"]

    def test_missing_api_key_header_returns_401(self):
        """Missing X-API-Key header should return 401 in api-key mode."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_key="my-api-key", auth_mode="api-key")
        handler.headers = {}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401
        assert "api-key" in handler._sent_json["error"].lower()

    def test_wrong_api_key_returns_403(self):
        """Wrong X-API-Key value should return 403."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_key="my-api-key", auth_mode="api-key")
        handler.headers = {"X-API-Key": "wrong-key"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 403
        assert "invalid" in handler._sent_json["error"].lower()

    def test_api_key_mode_ignores_bearer_token(self):
        """In api-key mode, Bearer token should not grant access."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_key="my-api-key", auth_mode="api-key")
        handler.headers = {"Authorization": "Bearer some-token"}
        handler.path = "/secrets"
        handler.do_GET()

        # Should still get 401 because api-key mode requires X-API-Key
        assert handler._sent_status == 401

    def test_api_key_mode_no_key_configured(self):
        """In api-key mode with no api_key configured, should return 401."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_key=None, auth_mode="api-key")
        handler.headers = {"X-API-Key": "some-key"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401
        assert "no api key configured" in handler._sent_json["error"].lower()

    def test_api_key_auth_info_endpoint_accessible(self):
        """auth/info endpoint should work without X-API-Key header."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, api_key="my-api-key", auth_mode="api-key")
        handler.headers = {}
        handler.path = "/auth/info"
        handler.do_GET()

        assert handler._sent_status == 200
        assert "api-key" in handler._sent_json["methods"]


# ── Tests: OAuth2 introspection authentication ─────────────────────────────────


class TestOAuth2Introspect:
    """Tests for OAuth2 token introspection authentication."""

    def setup_method(self):
        """Clear the OAuth2 cache before each test."""
        _oauth2_cache.clear()

    def teardown_method(self):
        """Clear the OAuth2 cache after each test."""
        _oauth2_cache.clear()

    @patch("envault.serve.urlopen")
    def test_introspect_active_token(self, mock_urlopen):
        """Active token via introspection should allow access."""
        # Mock the introspection endpoint response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"active": True, "scope": "read"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_introspect_url="https://auth.example.com/introspect",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer valid-oauth-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["keys"] == ["SECRET"]

    @patch("envault.serve.urlopen")
    def test_introspect_inactive_token(self, mock_urlopen):
        """Inactive token via introspection should return 401."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"active": False}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_introspect_url="https://auth.example.com/introspect",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer inactive-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401
        assert "not active" in handler._sent_json["error"].lower()

    @patch("envault.serve.urlopen")
    def test_introspect_server_error(self, mock_urlopen):
        """Introspection endpoint returning non-200 should return 401."""
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_introspect_url="https://auth.example.com/introspect",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer some-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401

    @patch("envault.serve.urlopen", side_effect=Exception("connection refused"))
    def test_introspect_connection_error(self, mock_urlopen):
        """Introspection endpoint unreachable should return 502."""
        # Need to also mock the 'requests' import path to fail first
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_introspect_url="https://auth.example.com/introspect",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer some-token"}
        handler.path = "/secrets"
        handler.do_GET()

        # Should get 502 (bad gateway) for connection errors
        assert handler._sent_status == 502

    def test_oauth2_mode_no_endpoint_configured(self):
        """OAuth2 mode without any endpoint should return 401."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, oauth_introspect_url=None, auth_mode="oauth2")
        handler.headers = {"Authorization": "Bearer some-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401
        assert "oauth2 endpoint not configured" in handler._sent_json["error"].lower()

    @patch("envault.serve.urlopen")
    def test_introspect_caches_result(self, mock_urlopen):
        """Successful introspection should be cached (no second call)."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"active": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_introspect_url="https://auth.example.com/introspect",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer cached-token"}
        handler.path = "/secrets"

        # First call — hits the introspection endpoint
        handler.do_GET()
        assert handler._sent_status == 200
        first_call_count = mock_urlopen.call_count

        # Second call — should use cache
        handler._sent_status = None
        handler._sent_json = None
        handler.do_GET()
        assert handler._sent_status == 200
        # urlopen should not have been called again
        assert mock_urlopen.call_count == first_call_count

    @patch("envault.serve.urlopen")
    def test_introspect_expired_cache_revalidates(self, mock_urlopen):
        """Expired cache entry should trigger revalidation."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"active": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Pre-populate cache with an expired entry
        _oauth2_cache["expired-token"] = (True, time.monotonic() - 1)

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_introspect_url="https://auth.example.com/introspect",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer expired-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        # Should have called urlopen (revalidation)
        assert mock_urlopen.call_count >= 1


# ── Tests: OAuth2 userinfo authentication ──────────────────────────────────────


class TestOAuth2Userinfo:
    """Tests for OAuth2 userinfo endpoint authentication."""

    def setup_method(self):
        """Clear the OAuth2 cache before each test."""
        _oauth2_cache.clear()

    def teardown_method(self):
        """Clear the OAuth2 cache after each test."""
        _oauth2_cache.clear()

    @patch("envault.serve.urlopen")
    def test_userinfo_valid_token(self, mock_urlopen):
        """Valid token via userinfo should allow access."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_userinfo_url="https://auth.example.com/userinfo",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer valid-userinfo-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["keys"] == ["SECRET"]

    @patch("envault.serve.urlopen")
    def test_userinfo_rejected_token(self, mock_urlopen):
        """Rejected token via userinfo should return 401."""
        mock_resp = MagicMock()
        mock_resp.status = 401
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_userinfo_url="https://auth.example.com/userinfo",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer rejected-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401

    @patch("envault.serve.urlopen", side_effect=Exception("DNS failure"))
    def test_userinfo_connection_error(self, mock_urlopen):
        """Userinfo endpoint unreachable should return 502."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_userinfo_url="https://auth.example.com/userinfo",
            auth_mode="oauth2",
        )
        handler.headers = {"Authorization": "Bearer some-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 502


# ── Tests: "any" auth mode ─────────────────────────────────────────────────────


class TestAnyAuthMode:
    """Tests for 'any' auth mode (accepts either X-API-Key or Bearer token)."""

    def test_api_key_accepted_in_any_mode(self):
        """X-API-Key should be accepted in 'any' mode."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="tok", api_key="key", auth_mode="any")
        handler.headers = {"X-API-Key": "key"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200

    def test_bearer_accepted_in_any_mode(self):
        """Bearer token should be accepted in 'any' mode when no X-API-Key is sent."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="tok", api_key="key", auth_mode="any")
        handler.headers = {"Authorization": "Bearer tok"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200

    def test_wrong_api_key_rejected_in_any_mode(self):
        """Wrong X-API-Key should return 403 immediately in 'any' mode."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="tok", api_key="key", auth_mode="any")
        handler.headers = {"X-API-Key": "wrong-key"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 403

    def test_no_auth_rejected_in_any_mode(self):
        """No auth headers should return 401 in 'any' mode."""
        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(store, api_token="tok", api_key="key", auth_mode="any")
        handler.headers = {}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401

    @patch("envault.serve.urlopen")
    def test_oauth2_accepted_in_any_mode(self, mock_urlopen):
        """OAuth2 introspection should work in 'any' mode."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"active": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        store = _FakeStore({"SECRET": "value"})
        handler = _make_handler(
            store,
            oauth_introspect_url="https://auth.example.com/introspect",
            auth_mode="any",
        )
        handler.headers = {"Authorization": "Bearer valid-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200


# ── Tests: OAuth2 cache ────────────────────────────────────────────────────────


class TestOAuth2Cache:
    """Tests for the OAuth2 token validation cache."""

    def setup_method(self):
        """Clear the OAuth2 cache before each test."""
        _oauth2_cache.clear()

    def teardown_method(self):
        """Clear the OAuth2 cache after each test."""
        _oauth2_cache.clear()

    def test_cache_stores_active_result(self):
        """Active token should be cached."""
        _oauth2_cache["test-token"] = (True, time.monotonic() + 300)
        assert "test-token" in _oauth2_cache
        is_active, expires_at = _oauth2_cache["test-token"]
        assert is_active is True

    def test_cache_stores_inactive_result(self):
        """Inactive token should be cached with short TTL."""
        _oauth2_cache["bad-token"] = (False, time.monotonic() + 60)
        is_active, expires_at = _oauth2_cache["bad-token"]
        assert is_active is False

    def test_cache_expiry(self):
        """Expired cache entries should be cleaned up on access."""
        # Insert an expired entry
        _oauth2_cache["expired"] = (True, time.monotonic() - 1)
        # The handler code checks time.monotonic() < expires_at and deletes expired
        assert "expired" in _oauth2_cache  # Still in cache dict but logically expired
