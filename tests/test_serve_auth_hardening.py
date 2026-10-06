"""Dummy-only regressions for default auth and the CLI-to-server boundary."""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

import envault.cli as cli_module
import envault.serve as serve_module
from envault.config import EnvaultConfig

AUTH_ENVIRONMENTS = (
    "ENVAULT_API_KEY",
    "ENVAULT_API_TOKEN",
    "ENVAULT_OAUTH_INTROSPECT_URL",
    "ENVAULT_OAUTH_USERINFO_URL",
    "ENVAULT_OAUTH_CLIENT_ID",
    "ENVAULT_OAUTH_CLIENT_SECRET",
)
SECRET_PATHS = ("/secrets", "/secrets/SAMPLE")


class _MemoryStore:
    def list_keys(self, prefix=""):
        return [key for key in ["SAMPLE"] if key.startswith(prefix)]

    def get(self, key):
        return "fixture-value" if key == "SAMPLE" else None


@pytest.fixture
def servers(monkeypatch):
    """Isolate credentials and capture server construction without sockets."""
    instances = []

    class NonBindingServer:
        def __init__(self, address, handler_class):
            self.address = address
            self.handler_class = handler_class
            instances.append(self)

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    for name in AUTH_ENVIRONMENTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(serve_module, "HTTPServer", NonBindingServer)
    monkeypatch.setattr(serve_module, "get_store", lambda _config: _MemoryStore())
    monkeypatch.setattr(cli_module, "load_config", lambda _path: EnvaultConfig())
    return instances


def _request(handler_class, path, headers):
    handler = object.__new__(handler_class)
    handler.path = path
    handler.headers = headers
    response = {}
    handler._send_json = lambda payload, status=200: response.update(status=status, payload=payload)
    handler._send_error = lambda status, message: response.update(status=status, payload={"error": message})
    handler.do_GET()
    return response


def _assert_authenticated(response, path):
    assert response["status"] == 200
    if path == "/secrets":
        assert response["payload"]["keys"] == ["SAMPLE"]
    else:
        assert response["payload"] == {"key": "SAMPLE", "value": "fixture-value"}


@pytest.mark.parametrize("path", SECRET_PATHS)
@pytest.mark.parametrize("auth_mode", ["any", "api-key"])
def test_api_key_only_rejects_bearer_bypass(servers, path, auth_mode):
    serve_module.run_server(
        EnvaultConfig(),
        host="0.0.0.0",
        encrypt_key="fixture-encryption-key",
        api_key="fixture-api-key",
        auth_mode=auth_mode,
    )
    handler_class = servers[0].handler_class
    for headers in (
        {},
        {"Authorization": "Basic fixture"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer incorrect"},
        {"X-API-Key": "incorrect"},
    ):
        assert _request(handler_class, path, headers)["status"] == 401
    _assert_authenticated(_request(handler_class, path, {"X-API-Key": "fixture-api-key"}), path)


@pytest.mark.parametrize("path", SECRET_PATHS)
def test_bearer_mode_without_static_token_rejects_empty_token(servers, path):
    serve_module.run_server(
        EnvaultConfig(),
        host="0.0.0.0",
        encrypt_key="fixture-encryption-key",
        api_key="fixture-api-key",
        auth_mode="bearer",
    )
    handler_class = servers[0].handler_class
    assert _request(handler_class, path, {"Authorization": "Bearer "})["status"] == 401
    assert _request(handler_class, path, {"X-API-Key": "fixture-api-key"})["status"] == 401


@pytest.mark.parametrize("path", SECRET_PATHS)
@pytest.mark.parametrize("auth_mode", ["any", "bearer"])
def test_static_token_validation_is_preserved(servers, path, auth_mode):
    serve_module.run_server(
        EnvaultConfig(),
        host="0.0.0.0",
        encrypt_key="fixture-encryption-key",
        api_token="fixture-static-token",
        auth_mode=auth_mode,
    )
    handler_class = servers[0].handler_class
    for headers in ({}, {"Authorization": "Bearer "}, {"Authorization": "Bearer incorrect"}):
        assert _request(handler_class, path, headers)["status"] == 401
    _assert_authenticated(_request(handler_class, path, {"Authorization": "Bearer fixture-static-token"}), path)


@pytest.mark.parametrize("path", SECRET_PATHS)
@pytest.mark.parametrize("auth_mode", ["any", "bearer", "oauth2"])
@pytest.mark.parametrize(
    ("endpoint", "validator"),
    [("oauth_introspect_url", "_oauth2_introspect"), ("oauth_userinfo_url", "_oauth2_userinfo")],
)
def test_oauth_validation_is_preserved_without_provider_calls(
    servers, monkeypatch, path, auth_mode, endpoint, validator
):
    calls = []

    def validate(handler, token):
        calls.append(token)
        if token == "fixture-oauth-token":
            return True
        handler._send_error(401, "Unauthorized: fixture token rejected")
        return False

    monkeypatch.setattr(serve_module.SecretHandler, validator, validate)
    serve_module.run_server(
        EnvaultConfig(),
        host="0.0.0.0",
        encrypt_key="fixture-encryption-key",
        api_token="fixture-static-token",
        auth_mode=auth_mode,
        **{endpoint: "https://identity.invalid/oauth"},
    )
    handler_class = servers[0].handler_class
    for headers in ({}, {"Authorization": "Bearer "}):
        assert _request(handler_class, path, headers)["status"] == 401
    assert calls == []
    for token in ("incorrect", "fixture-static-token"):
        assert _request(handler_class, path, {"Authorization": f"Bearer {token}"})["status"] == 401
    _assert_authenticated(_request(handler_class, path, {"Authorization": "Bearer fixture-oauth-token"}), path)
    assert calls == ["incorrect", "fixture-static-token", "fixture-oauth-token"]


@pytest.mark.parametrize("path", SECRET_PATHS)
@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_cli_api_token_overrides_environment_and_protects_secret_routes(servers, monkeypatch, path, host):
    monkeypatch.setenv("ENVAULT_API_TOKEN", "fixture-environment-token")
    result = CliRunner().invoke(
        cli_module.app,
        ["serve", "--host", host, "--password", "fixture-encryption-key", "--api-token", "fixture-cli-token"],
    )
    assert result.exit_code == 0, result.output
    assert len(servers) == 1
    assert servers[0].address == (host, 8080)
    handler_class = servers[0].handler_class
    assert handler_class.api_token == "fixture-cli-token"
    for headers in (
        {},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer incorrect"},
        {"Authorization": "Bearer fixture-environment-token"},
    ):
        assert _request(handler_class, path, headers)["status"] == 401
    _assert_authenticated(_request(handler_class, path, {"Authorization": "Bearer fixture-cli-token"}), path)
    assert "fixture-cli-token" not in result.output


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_cli_api_token_works_without_auth_environment(servers, host):
    result = CliRunner().invoke(
        cli_module.app,
        ["serve", "--host", host, "--password", "fixture-encryption-key", "--api-token", "fixture-cli-token"],
    )
    assert result.exit_code == 0, result.output
    assert len(servers) == 1
    assert servers[0].handler_class.api_token == "fixture-cli-token"


def test_cli_external_binding_without_credentials_still_fails_closed(servers):
    result = CliRunner().invoke(cli_module.app, ["serve", "--host", "0.0.0.0", "--password", "fixture-encryption-key"])
    assert result.exit_code != 0
    assert "API authentication required" in result.output
    assert servers == []


def test_cli_api_key_help_names_the_correct_header():
    result = CliRunner().invoke(cli_module.app, ["serve", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "X-API-Key" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)
