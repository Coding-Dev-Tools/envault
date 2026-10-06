"""Regression coverage for authentication passed from run_server to handlers."""

from __future__ import annotations

import pytest

import envault.serve as serve_module
from envault.config import EnvaultConfig
from envault.serve import SecretHandler

AUTH_ENVIRONMENTS = (
    "ENVAULT_API_KEY",
    "ENVAULT_API_TOKEN",
    "ENVAULT_OAUTH_INTROSPECT_URL",
    "ENVAULT_OAUTH_USERINFO_URL",
    "ENVAULT_OAUTH_CLIENT_ID",
    "ENVAULT_OAUTH_CLIENT_SECRET",
)


class _MemoryStore:
    def list_keys(self, prefix: str = "") -> list[str]:
        keys = ["SAMPLE"]
        return [key for key in keys if key.startswith(prefix)]

    def get(self, key: str) -> str | None:
        return "example" if key == "SAMPLE" else None


class _NonBindingServer:
    """Capture the handler factory without opening a listening socket."""

    instances = []

    def __init__(self, address, handler_class):
        self.address = address
        self.handler_class = handler_class
        self.instances.append(self)

    def serve_forever(self) -> None:
        return None

    def server_close(self) -> None:
        return None


def _start_with_dummy_environment(monkeypatch, *, auth_mode: str = "any", **environment: str):
    _NonBindingServer.instances.clear()
    for name in AUTH_ENVIRONMENTS:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    monkeypatch.setattr(serve_module, "HTTPServer", _NonBindingServer)
    monkeypatch.setattr(serve_module, "get_store", lambda _config: _MemoryStore())
    serve_module.run_server(
        config=EnvaultConfig(),
        host="0.0.0.0",
        encrypt_key="fixture-encryption-key",
        auth_mode=auth_mode,
    )
    assert len(_NonBindingServer.instances) == 1
    return _NonBindingServer.instances[0].handler_class


def _request(handler_class, path: str, headers: dict[str, str]):
    """Create an in-memory request handler with no server or network I/O."""
    instance = object.__new__(handler_class)
    instance.command = "GET"
    instance.path = path
    instance.headers = headers
    instance._sent_json = None
    instance._sent_status = None

    def capture_json(payload, status=200):
        instance._sent_json = payload
        instance._sent_status = status

    instance._send_json = capture_json
    instance._send_error = lambda status, message: capture_json({"error": message}, status)
    return instance


def test_token_only_environment_requires_a_valid_bearer_token(monkeypatch, capsys):
    token = "fixture-token-314"
    handler_class = _start_with_dummy_environment(
        monkeypatch,
        ENVAULT_API_TOKEN=token,
    )

    assert handler_class.api_token == token
    assert handler_class.api_key is None
    assert handler_class.auth_mode == "any"
    startup_output = capsys.readouterr().out
    assert "API authentication enabled" in startup_output
    assert token not in startup_output

    auth_info = _request(handler_class, "/auth/info", {})
    auth_info.do_GET()
    assert auth_info._sent_json["requires_auth"] is True
    assert auth_info._sent_json["methods"] == ["bearer"]
    assert token not in str(auth_info._sent_json)

    unauthenticated = _request(handler_class, "/secrets", {})
    unauthenticated.do_GET()
    assert unauthenticated._sent_status == 401

    wrong = _request(handler_class, "/secrets", {"Authorization": "Bearer fixture-token-271"})
    wrong.do_GET()
    assert wrong._sent_status == 401

    authenticated = _request(handler_class, "/secrets", {"Authorization": f"Bearer {token}"})
    authenticated.do_GET()
    assert authenticated._sent_status == 200
    assert authenticated._sent_json["keys"] == ["SAMPLE"]


def test_api_key_environment_remains_forwarded(monkeypatch):
    api_key = "fixture-api-key-314"
    handler_class = _start_with_dummy_environment(
        monkeypatch,
        ENVAULT_API_KEY=api_key,
        auth_mode="api-key",
    )

    assert handler_class.api_key == api_key
    assert handler_class.api_token is None

    unauthenticated = _request(handler_class, "/secrets", {})
    unauthenticated.do_GET()
    assert unauthenticated._sent_status == 401

    authenticated = _request(handler_class, "/secrets", {"X-API-Key": api_key})
    authenticated.do_GET()
    assert authenticated._sent_status == 200
    assert authenticated._sent_json["keys"] == ["SAMPLE"]


@pytest.mark.parametrize(
    ("endpoint_environment", "handler_attribute", "auth_method", "validator"),
    [
        (
            "ENVAULT_OAUTH_INTROSPECT_URL",
            "oauth_introspect_url",
            "oauth2-introspect",
            "_oauth2_introspect",
        ),
        (
            "ENVAULT_OAUTH_USERINFO_URL",
            "oauth_userinfo_url",
            "oauth2-userinfo",
            "_oauth2_userinfo",
        ),
    ],
)
def test_oauth_environment_requires_a_validated_bearer_token(
    monkeypatch, endpoint_environment, handler_attribute, auth_method, validator
):
    endpoint = "https://identity.invalid/oauth"
    client_id = "fixture-client-271"
    client_secret = "fixture-client-secret-314"

    def validate_dummy_token(handler, value):
        if value == "fixture-oauth-token-314":
            return True
        handler._send_error(401, "Unauthorized: dummy token rejected")
        return False

    monkeypatch.setattr(serve_module, "_oauth2_cache", {})
    monkeypatch.setattr(
        SecretHandler,
        validator,
        validate_dummy_token,
    )
    handler_class = _start_with_dummy_environment(
        monkeypatch,
        **{
            endpoint_environment: endpoint,
            "ENVAULT_OAUTH_CLIENT_ID": client_id,
            "ENVAULT_OAUTH_CLIENT_SECRET": client_secret,
        },
        auth_mode="oauth2",
    )

    assert getattr(handler_class, handler_attribute) == endpoint
    assert handler_class.oauth_client_id == client_id
    assert handler_class.oauth_client_secret == client_secret
    assert handler_class.auth_mode == "oauth2"

    auth_info = _request(handler_class, "/auth/info", {})
    auth_info.do_GET()
    assert auth_info._sent_json["requires_auth"] is True
    assert auth_info._sent_json["methods"] == [auth_method]
    assert client_secret not in str(auth_info._sent_json)

    unauthenticated = _request(handler_class, "/secrets", {})
    unauthenticated.do_GET()
    assert unauthenticated._sent_status == 401

    invalid = _request(handler_class, "/secrets", {"Authorization": "Bearer invalid-fixture-token"})
    invalid.do_GET()
    assert invalid._sent_status == 401

    authenticated = _request(
        handler_class,
        "/secrets",
        {"Authorization": "Bearer fixture-oauth-token-314"},
    )
    authenticated.do_GET()
    assert authenticated._sent_status == 200
    assert authenticated._sent_json["keys"] == ["SAMPLE"]


def test_non_localhost_binding_still_rejects_missing_credentials(monkeypatch):
    for name in AUTH_ENVIRONMENTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        serve_module,
        "HTTPServer",
        lambda *_args: pytest.fail("An unauthenticated server must not be constructed"),
    )
    monkeypatch.setattr(serve_module, "get_store", lambda _config: pytest.fail("The store must not be read"))

    with pytest.raises(SystemExit, match="API authentication required"):
        serve_module.run_server(
            config=EnvaultConfig(),
            host="0.0.0.0",
            encrypt_key="fixture-encryption-key",
        )
