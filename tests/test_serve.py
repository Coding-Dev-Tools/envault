"""Auto-generated tests for envault.serve."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest

from envault.config import EnvaultConfig
from envault.serve import SecretHandler, create_handler

# ── Fixtures ────────────────────────────────────────────────────────────────


class _FakeStore:
    """Minimal in-memory secret store for testing."""

    def __init__(self, data: dict[str, str]) -> None:
        self._data = dict(data)

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> bool:
        self._data[key] = value
        return True

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        if prefix:
            return [k for k in self._data if k.startswith(prefix)]
        return list(self._data.keys())


# ── create_handler ──────────────────────────────────────────────────────────────


def test_create_handler(
    store=...,
    config=...,
    encrypt_key=None,
    api_token=None,
    api_key=None,
    auth_mode="bearer",
    oauth_introspect_url=None,
    oauth_userinfo_url=None,
    oauth_client_id=None,
    oauth_client_secret=None,
):
    """Return a BaseHTTPRequestHandler subclass bound to the given store/config."""
    # TODO: implement test for create_handler
    # result = serve.create_handler(...)
    # function returns None — verify no exception raised


@pytest.mark.parametrize(
    "store",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_store_edge_cases(
    store,
    config=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
    oauth_client_id=...,
    oauth_client_secret=...,
):
    """Edge cases for create_handler param store."""
    # TODO: call serve.create_handler with edge-case store
    pass


@pytest.mark.parametrize(
    "config",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_config_edge_cases(
    config,
    store=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
    oauth_client_id=...,
    oauth_client_secret=...,
):
    """Edge cases for create_handler param config."""
    # TODO: call serve.create_handler with edge-case config
    pass


def _make_handler(
    store, config: EnvaultConfig | None = None, api_key: str | None = None
):
    """Create a handler class bound to the given store and return a mock instance.

    We create a mock request handler that has the routing logic from
    SecretHandler but uses pre-set wfile/rfile so we can inspect output.
    """
    config = config or EnvaultConfig()
    # api_token mirrors api_key so Bearer auth works in tests
    handler_class = create_handler(
        store,
        config,
        encrypt_key="test-key",
        api_key=api_key,
        api_token=api_key,
        auth_mode="bearer" if api_key else "any",
    )
    return _build_handler_instance(handler_class)


@pytest.mark.parametrize(
    "api_token",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_api_token_edge_cases(
    api_token,
    store=...,
    config=...,
    encrypt_key=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
    oauth_client_id=...,
    oauth_client_secret=...,
):
    """Edge cases for create_handler param api_token."""
    # TODO: call serve.create_handler with edge-case api_token
    pass


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

    instance._send_json = lambda data, status=200: _capturing_send_json(
        instance, data, status
    )

    return instance


@pytest.mark.parametrize(
    "auth_mode",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_auth_mode_edge_cases(
    auth_mode,
    store=...,
    config=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
    oauth_client_id=...,
    oauth_client_secret=...,
):
    """Edge cases for create_handler param auth_mode."""
    # TODO: call serve.create_handler with edge-case auth_mode
    pass


@pytest.mark.parametrize(
    "oauth_introspect_url",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_oauth_introspect_url_edge_cases(
    oauth_introspect_url,
    store=...,
    config=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_userinfo_url=...,
    oauth_client_id=...,
    oauth_client_secret=...,
):
    """Edge cases for create_handler param oauth_introspect_url."""
    # TODO: call serve.create_handler with edge-case oauth_introspect_url
    pass


@pytest.mark.parametrize(
    "oauth_userinfo_url",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_oauth_userinfo_url_edge_cases(
    oauth_userinfo_url,
    store=...,
    config=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_client_id=...,
    oauth_client_secret=...,
):
    """Edge cases for create_handler param oauth_userinfo_url."""
    # TODO: call serve.create_handler with edge-case oauth_userinfo_url
    pass


@pytest.mark.parametrize(
    "oauth_client_id",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_oauth_client_id_edge_cases(
    oauth_client_id,
    store=...,
    config=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
    oauth_client_secret=...,
):
    """Edge cases for create_handler param oauth_client_id."""
    # TODO: call serve.create_handler with edge-case oauth_client_id
    pass


@pytest.mark.parametrize(
    "oauth_client_secret",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_create_handler_oauth_client_secret_edge_cases(
    oauth_client_secret,
    store=...,
    config=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
    oauth_client_id=...,
):
    """Edge cases for create_handler param oauth_client_secret."""
    # TODO: call serve.create_handler with edge-case oauth_client_secret
    pass


class TestSecretsList:
    """Tests for GET /secrets endpoint — list all keys."""

    def test_list_keys(self):
        store = _FakeStore(
            {"DB_HOST": "localhost", "DB_PORT": "5432", "API_KEY": "abc"}
        )
        handler = _make_handler(store)
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        data = handler._sent_json
        assert set(data["keys"]) == {"DB_HOST", "DB_PORT", "API_KEY"}
        assert data["count"] == 3

    def test_list_keys_with_prefix(self):
        store = _FakeStore(
            {"DB_HOST": "localhost", "DB_PORT": "5432", "API_KEY": "abc"}
        )
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


def test_run_server(
    config=...,
    port=8080,
    host="127.0.0.1",
    encrypt_key=None,
    store_name=None,
    api_token=None,
    api_key=None,
    auth_mode="bearer",
    oauth_introspect_url=None,
    oauth_userinfo_url=None,
):
    """Start the HTTP server for the secrets API."""
    # TODO: implement test for run_server
    # result = serve.run_server(...)
    # assert result is not None


@pytest.mark.parametrize(
    "config",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_config_edge_cases(
    config,
    port=...,
    host=...,
    encrypt_key=...,
    store_name=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param config."""
    # TODO: call serve.run_server with edge-case config
    pass


@pytest.mark.parametrize(
    "port",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(999999, id="large"),
    ],
)
def test_run_server_port_edge_cases(
    port,
    config=...,
    host=...,
    encrypt_key=...,
    store_name=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param port."""
    # TODO: call serve.run_server with edge-case port
    pass


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_host_edge_cases(
    host,
    config=...,
    port=...,
    encrypt_key=...,
    store_name=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param host."""
    # TODO: call serve.run_server with edge-case host
    pass


@pytest.mark.parametrize(
    "encrypt_key",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_encrypt_key_edge_cases(
    encrypt_key,
    config=...,
    port=...,
    host=...,
    store_name=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param encrypt_key."""
    # TODO: call serve.run_server with edge-case encrypt_key
    pass


@pytest.mark.parametrize(
    "store_name",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_store_name_edge_cases(
    store_name,
    config=...,
    port=...,
    host=...,
    encrypt_key=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param store_name."""
    # TODO: call serve.run_server with edge-case store_name
    pass


@pytest.mark.parametrize(
    "api_token",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_api_token_edge_cases(
    api_token,
    config=...,
    port=...,
    host=...,
    encrypt_key=...,
    store_name=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param api_token."""
    # TODO: call serve.run_server with edge-case api_token
    pass


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


# ── Tests: API Authentication ──────────────────────────────────────────────────


class TestApiAuth:
    """Tests for Bearer token authentication on /secrets endpoints."""

    def test_no_auth_configured_allows_secrets(self):
        """Without api_key set, /secrets should be accessible."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key=None)
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200
        assert "DB_URL" in handler._sent_json["keys"]

    def test_no_auth_configured_allows_secrets_get(self):
        """Without api_key set, /secrets/{key} should be accessible."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key=None)
        handler.path = "/secrets/DB_URL"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["value"] == "postgres://localhost"

    def test_auth_valid_bearer_allows_secrets(self):
        """With correct Bearer token, /secrets should be accessible."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {"Authorization": "Bearer my-secret-key"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 200

    def test_auth_valid_bearer_allows_secrets_get(self):
        """With correct Bearer token, /secrets/{key} should be accessible."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {"Authorization": "Bearer my-secret-key"}
        handler.path = "/secrets/DB_URL"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["value"] == "postgres://localhost"

    def test_auth_missing_header_returns_401(self):
        """Without Authorization header when auth is enabled, should return 401."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401
        assert "unauthorized" in handler._sent_json["error"].lower()

    def test_auth_wrong_token_returns_401(self):
        """With incorrect Bearer token, should return 401."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {"Authorization": "Bearer wrong-token"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401

    def test_auth_wrong_token_returns_401_on_get_key(self):
        """With incorrect Bearer token on /secrets/{key}, should return 401."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {"Authorization": "Bearer wrong-token"}
        handler.path = "/secrets/DB_URL"
        handler.do_GET()

        assert handler._sent_status == 401

    def test_auth_malformed_header_returns_401(self):
        """With malformed Authorization header, should return 401."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {"Authorization": "Basic dXNlcjpwYXNz"}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401

    def test_health_always_accessible_with_auth(self):
        """GET /health should be accessible even without auth when api_key is set."""
        store = _FakeStore({"K": "v"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {}  # No auth header
        handler.path = "/health"
        handler.do_GET()

        assert handler._sent_status == 200
        assert handler._sent_json["status"] == "ok"

    def test_auth_empty_bearer_returns_401(self):
        """Bearer with empty token should return 401."""
        store = _FakeStore({"DB_URL": "postgres://localhost"})
        handler = _make_handler(store, api_key="my-secret-key")
        handler.headers = {"Authorization": "Bearer "}
        handler.path = "/secrets"
        handler.do_GET()

        assert handler._sent_status == 401


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

    def test_handler_class_with_api_key(self):
        """create_handler should bind api_key to the handler class."""
        store = _FakeStore({"X": "y"})
        handler_class = create_handler(
            store, EnvaultConfig(), encrypt_key="enc", api_key="api-token"
        )

        assert handler_class.api_key == "api-token"

    def test_handler_class_without_api_key(self):
        """create_handler with no api_key should set it to None."""
        store = _FakeStore({"X": "y"})
        handler_class = create_handler(store, EnvaultConfig(), encrypt_key="enc")

        assert handler_class.api_key is None


# ── Tests: CLI serve command ───────────────────────────────────────────────────


class TestServeCLI:
    """Test the 'serve' typer command (without actually starting the server)."""

    @staticmethod
    def _strip_ansi(text: str) -> str:
        import re

        return re.sub(r"\x1b\[[0-9;]*m", "", text)

    def test_serve_help(self):
        """serve --help should show endpoint descriptions."""
        from typer.testing import CliRunner

        from envault.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        clean = self._strip_ansi(result.stdout).lower()
        assert "port" in clean
        assert "health" in clean or "secrets" in clean

    def test_serve_help_shows_api_key_option(self):
        """serve --help should show the --api-key option."""
        from typer.testing import CliRunner

        from envault.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        clean = self._strip_ansi(result.stdout).lower()
        assert "api-key" in clean

    def test_serve_help_shows_default_host_localhost(self):
        """serve --help should show default host as 127.0.0.1."""
        from typer.testing import CliRunner

        from envault.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        clean = self._strip_ansi(result.stdout)
        assert "127.0.0.1" in clean

    def test_serve_no_encrypt_key_exits(self, tmp_path):
        """serve without any encryption key should exit with error."""


@pytest.mark.parametrize(
    "auth_mode",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_auth_mode_edge_cases(
    auth_mode,
    config=...,
    port=...,
    host=...,
    encrypt_key=...,
    store_name=...,
    api_token=...,
    api_key=...,
    oauth_introspect_url=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param auth_mode."""
    # TODO: call serve.run_server with edge-case auth_mode
    pass


@pytest.mark.parametrize(
    "oauth_introspect_url",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_oauth_introspect_url_edge_cases(
    oauth_introspect_url,
    config=...,
    port=...,
    host=...,
    encrypt_key=...,
    store_name=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_userinfo_url=...,
):
    """Edge cases for run_server param oauth_introspect_url."""
    # TODO: call serve.run_server with edge-case oauth_introspect_url
    pass


@pytest.mark.parametrize(
    "oauth_userinfo_url",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace"),
        pytest.param(
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            id="long_string",
        ),
        pytest.param("héllo wörld", id="unicode"),
        pytest.param("line1\nline2", id="with_newline"),
    ],
)
def test_run_server_oauth_userinfo_url_edge_cases(
    oauth_userinfo_url,
    config=...,
    port=...,
    host=...,
    encrypt_key=...,
    store_name=...,
    api_token=...,
    api_key=...,
    auth_mode=...,
    oauth_introspect_url=...,
):
    """Edge cases for run_server param oauth_userinfo_url."""
    # TODO: call serve.run_server with edge-case oauth_userinfo_url
    pass


# ── SecretHandler ───────────────────────────────────────────────────────────────


class TestSecretHandler:
    """Tests for SecretHandler."""

    def test_do_GET(
        self,
    ):
        """Smoke test for SecretHandler.do_GET."""
        # TODO: implement test for SecretHandler.do_GET
        # obj = SecretHandler(...)
        # result = obj.do_GET(...)
        # assert result is not None

    def test_log_message(self, format=...):
        """Quiet default logging — only log at debug level if needed."""
        # TODO: implement test for SecretHandler.log_message
        # obj = SecretHandler(...)
        # result = obj.log_message(...)
        # assert result is not None
