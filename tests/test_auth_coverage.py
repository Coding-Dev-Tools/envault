"""Coverage-driven regression tests for envault.auth module.

Closes gaps in BearerAuth, ApiKeyAuth, OAuth2Auth (userinfo strategy,
cache expiry, scope/audience validation, error paths), MultiAuth fallback
logic, and build_auth_from_env factory.
"""
from __future__ import annotations

import json
import time

from envault.auth import (
    ApiKeyAuth,
    AuthResult,
    BearerAuth,
    MultiAuth,
    OAuth2Auth,
    build_auth_from_env,
)


# ── AuthResult ───────────────────────────────────────────────────────────


class TestAuthResult:
    def test_ok_default_identity(self):
        r = AuthResult.ok()
        assert r.success is True
        assert r.identity == "anonymous"
        assert r.error_status == 401
        assert r.error_message == ""

    def test_ok_custom_identity(self):
        r = AuthResult.ok(identity="user:alice")
        assert r.success is True
        assert r.identity == "user:alice"

    def test_fail_default(self):
        r = AuthResult.fail()
        assert r.success is False
        assert r.error_status == 401
        assert r.error_message == "Unauthorized"

    def test_fail_custom(self):
        r = AuthResult.fail(status=403, message="Forbidden")
        assert r.success is False
        assert r.error_status == 403
        assert r.error_message == "Forbidden"


# ── BearerAuth ───────────────────────────────────────────────────────────


class TestBearerAuth:
    def test_valid_token(self):
        auth = BearerAuth("secret-token-12345")
        result = auth.check({"Authorization": "Bearer secret-token-12345"})
        assert result.success is True
        assert "bearer:" in result.identity

    def test_missing_header(self):
        auth = BearerAuth("token")
        result = auth.check({})
        assert result.success is False
        assert result.error_status == 401

    def test_non_bearer_scheme(self):
        auth = BearerAuth("token")
        result = auth.check({"Authorization": "Basic dXNlcjpwYXNz"})
        assert result.success is False
        assert result.error_status == 401
        assert "Bearer token required" in result.error_message

    def test_wrong_token(self):
        auth = BearerAuth("correct")
        result = auth.check({"Authorization": "Bearer wrong"})
        assert result.success is False
        assert result.error_status == 403
        assert "invalid token" in result.error_message

    def test_empty_bearer_value(self):
        auth = BearerAuth("token")
        result = auth.check({"Authorization": "Bearer "})
        assert result.success is False
        assert result.error_status == 403


# ── ApiKeyAuth ───────────────────────────────────────────────────────────


class TestApiKeyAuth:
    def test_valid_key_single(self):
        auth = ApiKeyAuth("my-api-key")
        result = auth.check({"X-Api-Key": "my-api-key"})
        assert result.success is True
        assert "api_key:" in result.identity

    def test_valid_key_uppercase_header(self):
        auth = ApiKeyAuth("my-api-key")
        result = auth.check({"X-API-KEY": "my-api-key"})
        assert result.success is True

    def test_comma_separated_keys(self):
        auth = ApiKeyAuth("key1, key2, key3")
        assert auth.check({"X-Api-Key": "key1"}).success
        assert auth.check({"X-Api-Key": "key2"}).success
        assert auth.check({"X-Api-Key": "key3"}).success
        assert not auth.check({"X-Api-Key": "key4"}).success

    def test_list_keys(self):
        auth = ApiKeyAuth(["a", "b"])
        assert auth.check({"X-Api-Key": "a"}).success
        assert not auth.check({"X-Api-Key": "c"}).success

    def test_missing_key(self):
        auth = ApiKeyAuth("key")
        result = auth.check({})
        assert result.success is False
        assert result.error_status == 401
        assert "API key required" in result.error_message

    def test_invalid_key(self):
        auth = ApiKeyAuth("valid")
        result = auth.check({"X-Api-Key": "invalid"})
        assert result.success is False
        assert result.error_status == 403
        assert "invalid API key" in result.error_message

    def test_empty_string_keys_stripped(self):
        auth = ApiKeyAuth("key1,,  ,key2")
        assert len(auth._keys) == 2


# ── OAuth2Auth ───────────────────────────────────────────────────────────


def _make_response(status: int, body: dict):
    """Create a mock urlopen response context manager."""

    class _Resp:
        def __init__(self):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(body).encode()

    return _Resp()


class TestOAuth2AuthUserinfo:
    def test_userinfo_success(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"sub": "user1", "email": "u@test.com"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example")
        result = auth.check({"Authorization": "Bearer valid-token"})
        assert result.success is True
        assert "oauth2:user1" in result.identity

    def test_userinfo_uses_email_fallback(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"email": "fallback@test.com"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is True
        assert "fallback@test.com" in result.identity

    def test_userinfo_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(401, {"error": "invalid_token"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example")
        result = auth.check({"Authorization": "Bearer bad-token"})
        assert result.success is False
        assert result.error_status == 401

    def test_missing_bearer_prefix(self):
        auth = OAuth2Auth(provider_url="https://idp.example")
        result = auth.check({"Authorization": "Basic abc"})
        assert result.success is False
        assert result.error_status == 401
        assert "Bearer token required" in result.error_message

    def test_no_auth_header(self):
        auth = OAuth2Auth(provider_url="https://idp.example")
        result = auth.check({})
        assert result.success is False
        assert result.error_status == 401


class TestOAuth2AuthIntrospect:
    def test_introspect_active(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"active": True, "sub": "client1"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example", strategy="introspect")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is True

    def test_introspect_inactive(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"active": False}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example", strategy="introspect")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is False
        assert result.error_status == 401
        assert "not active" in result.error_message

    def test_introspect_with_client_creds(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout=10):
            captured["headers"] = dict(req.headers)
            return _make_response(200, {"active": True, "sub": "svc"})

        monkeypatch.setattr("envault.auth.urlopen", fake_urlopen)
        auth = OAuth2Auth(
            provider_url="https://idp.example",
            strategy="introspect",
            client_id="cid",
            client_secret="csec",
        )
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is True
        assert "Basic" in captured["headers"].get("Authorization", "")


class TestOAuth2AuthCache:
    def test_cache_hit(self, monkeypatch):
        call_count = 0

        def fake_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            return _make_response(200, {"sub": "cached-user"})

        monkeypatch.setattr("envault.auth.urlopen", fake_urlopen)
        auth = OAuth2Auth(provider_url="https://idp.example", cache_ttl=60)

        r1 = auth.check({"Authorization": "Bearer tok"})
        r2 = auth.check({"Authorization": "Bearer tok"})
        assert r1.success and r2.success
        assert call_count == 1  # Second call served from cache

    def test_cache_expiry(self, monkeypatch):
        call_count = 0

        def fake_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            return _make_response(200, {"sub": "user"})

        monkeypatch.setattr("envault.auth.urlopen", fake_urlopen)
        auth = OAuth2Auth(provider_url="https://idp.example", cache_ttl=1)

        auth.check({"Authorization": "Bearer tok"})
        assert call_count == 1

        # Simulate cache expiry by manipulating internal state
        for token_key in list(auth._cache.keys()):
            identity, _ = auth._cache[token_key]
            auth._cache[token_key] = (identity, time.monotonic() - 1)

        auth.check({"Authorization": "Bearer tok"})
        assert call_count == 2  # Cache expired, re-validated


class TestOAuth2AuthScopeAudience:
    def test_scope_present(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"sub": "u", "scope": "read write admin"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example", required_scope="read write")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is True

    def test_scope_missing(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"sub": "u", "scope": "read"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example", required_scope="read write")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is False
        assert result.error_status == 403
        assert "missing scope" in result.error_message
        assert "write" in result.error_message

    def test_audience_string_match(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"sub": "u", "aud": "my-api"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example", required_audience="my-api")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is True

    def test_audience_list_match(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"sub": "u", "aud": ["api-a", "api-b"]}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example", required_audience="api-b")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is True

    def test_audience_mismatch(self, monkeypatch):
        monkeypatch.setattr(
            "envault.auth.urlopen",
            lambda req, timeout=10: _make_response(200, {"sub": "u", "aud": "other-api"}),
        )
        auth = OAuth2Auth(provider_url="https://idp.example", required_audience="my-api")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is False
        assert result.error_status == 403
        assert "invalid audience" in result.error_message


class TestOAuth2AuthErrors:
    def test_url_error(self, monkeypatch):
        from urllib.error import URLError

        def fake_urlopen(req, timeout=10):
            raise URLError(reason="connection refused")

        monkeypatch.setattr("envault.auth.urlopen", fake_urlopen)
        auth = OAuth2Auth(provider_url="https://idp.example")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is False
        assert result.error_status == 502
        assert "unreachable" in result.error_message

    def test_generic_exception(self, monkeypatch):
        def fake_urlopen(req, timeout=10):
            raise RuntimeError("unexpected")

        monkeypatch.setattr("envault.auth.urlopen", fake_urlopen)
        auth = OAuth2Auth(provider_url="https://idp.example")
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is False
        assert result.error_status == 502
        assert "validation error" in result.error_message


# ── MultiAuth ────────────────────────────────────────────────────────────


class TestMultiAuth:
    def test_open_mode_no_backends(self):
        auth = MultiAuth()
        result = auth.check({})
        assert result.success is True
        assert result.identity == "open"
        assert auth.is_enabled is False

    def test_empty_list_is_open(self):
        auth = MultiAuth([])
        assert auth.is_enabled is False
        assert auth.check({}).success is True

    def test_first_backend_wins(self):
        auth = MultiAuth([BearerAuth("tok"), ApiKeyAuth("key")])
        assert auth.is_enabled is True
        result = auth.check({"Authorization": "Bearer tok"})
        assert result.success is True
        assert "bearer:" in result.identity

    def test_falls_through_to_second(self):
        auth = MultiAuth([BearerAuth("tok"), ApiKeyAuth("key")])
        result = auth.check({"X-Api-Key": "key"})
        assert result.success is True
        assert "api_key:" in result.identity

    def test_returns_most_specific_failure(self):
        """When all backends fail, prefer 403 (wrong creds) over 401 (no creds)."""
        auth = MultiAuth([BearerAuth("correct"), ApiKeyAuth("correct")])
        # Wrong bearer → 403; missing api key → 401. Should return 403.
        result = auth.check({"Authorization": "Bearer wrong"})
        assert result.success is False
        assert result.error_status == 403

    def test_all_missing_returns_401(self):
        auth = MultiAuth([BearerAuth("tok"), ApiKeyAuth("key")])
        result = auth.check({})
        assert result.success is False
        assert result.error_status == 401


# ── build_auth_from_env ──────────────────────────────────────────────────


class TestBuildAuthFromEnv:
    def test_empty_env_is_open(self, monkeypatch):
        for var in [
            "ENVAULT_API_TOKEN",
            "ENVAULT_API_KEY",
            "ENVAULT_OAUTH2_URL",
        ]:
            monkeypatch.delenv(var, raising=False)
        auth = build_auth_from_env()
        assert auth.is_enabled is False

    def test_bearer_only(self, monkeypatch):
        monkeypatch.setenv("ENVAULT_API_TOKEN", "my-token")
        monkeypatch.delenv("ENVAULT_API_KEY", raising=False)
        monkeypatch.delenv("ENVAULT_OAUTH2_URL", raising=False)
        auth = build_auth_from_env()
        assert auth.is_enabled is True
        result = auth.check({"Authorization": "Bearer my-token"})
        assert result.success is True

    def test_api_key_only(self, monkeypatch):
        monkeypatch.delenv("ENVAULT_API_TOKEN", raising=False)
        monkeypatch.setenv("ENVAULT_API_KEY", "k1,k2")
        monkeypatch.delenv("ENVAULT_OAUTH2_URL", raising=False)
        auth = build_auth_from_env()
        assert auth.is_enabled is True
        assert auth.check({"X-Api-Key": "k1"}).success
        assert auth.check({"X-Api-Key": "k2"}).success

    def test_oauth2_configured(self, monkeypatch):
        monkeypatch.delenv("ENVAULT_API_TOKEN", raising=False)
        monkeypatch.delenv("ENVAULT_API_KEY", raising=False)
        monkeypatch.setenv("ENVAULT_OAUTH2_URL", "https://idp.example")
        monkeypatch.setenv("ENVAULT_OAUTH2_STRATEGY", "introspect")
        monkeypatch.setenv("ENVAULT_OAUTH2_CLIENT_ID", "cid")
        monkeypatch.setenv("ENVAULT_OAUTH2_CLIENT_SECRET", "csec")
        monkeypatch.setenv("ENVAULT_OAUTH2_SCOPE", "read")
        monkeypatch.setenv("ENVAULT_OAUTH2_AUDIENCE", "api")
        auth = build_auth_from_env()
        assert auth.is_enabled is True
        assert len(auth._backends) == 1
        backend = auth._backends[0]
        assert isinstance(backend, OAuth2Auth)
        assert backend._strategy == "introspect"
        assert backend._required_scope == "read"
        assert backend._required_audience == "api"

    def test_all_backends_combined(self, monkeypatch):
        monkeypatch.setenv("ENVAULT_API_TOKEN", "tok")
        monkeypatch.setenv("ENVAULT_API_KEY", "key")
        monkeypatch.setenv("ENVAULT_OAUTH2_URL", "https://idp.example")
        auth = build_auth_from_env()
        assert len(auth._backends) == 3
