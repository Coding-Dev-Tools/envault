"""Authentication backends for the envault serve HTTP API.

Supported methods:
  - bearer:  Static Bearer token (existing, simplest)
  - api_key: Static API key via X-API-Key header (common for service-to-service)
  - oauth2:  OAuth2 token validation via introspection or userinfo endpoint

The handler's _check_auth() delegates to whichever backend is configured.
Multiple backends can be enabled simultaneously — the first successful check wins.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class AuthResult:
    """Outcome of an authentication check."""

    __slots__ = ("success", "identity", "error_status", "error_message")

    def __init__(
        self,
        *,
        success: bool,
        identity: str | None = None,
        error_status: int = 401,
        error_message: str = "",
    ) -> None:
        self.success = success
        self.identity = identity
        self.error_status = error_status
        self.error_message = error_message

    @classmethod
    def ok(cls, identity: str = "anonymous") -> AuthResult:
        return cls(success=True, identity=identity)

    @classmethod
    def fail(cls, status: int = 401, message: str = "Unauthorized") -> AuthResult:
        return cls(success=False, error_status=status, error_message=message)


class BearerAuth:
    """Validate a static Bearer token (the pre-existing auth mode)."""

    def __init__(self, token: str) -> None:
        self._token = token

    def check(self, headers: dict[str, str]) -> AuthResult:
        auth_header = headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return AuthResult.fail(401, "Unauthorized: Bearer token required")

        token = auth_header[len("Bearer "):]
        if token != self._token:
            return AuthResult.fail(403, "Forbidden: invalid token")

        return AuthResult.ok(identity=f"bearer:{token[:8]}…")


class ApiKeyAuth:
    """Validate an API key sent via the X-API-Key header.

    Supports a single key or a set of keys (comma-separated env var).
    """

    def __init__(self, valid_keys: str | list[str]) -> None:
        if isinstance(valid_keys, str):
            # Comma-separated in env var
            self._keys = {k.strip() for k in valid_keys.split(",") if k.strip()}
        else:
            self._keys = set(valid_keys)

    def check(self, headers: dict[str, str]) -> AuthResult:
        api_key = headers.get("X-Api-Key", "") or headers.get("X-API-KEY", "")
        if not api_key:
            return AuthResult.fail(401, "Unauthorized: API key required (X-API-Key header)")

        if api_key not in self._keys:
            return AuthResult.fail(403, "Forbidden: invalid API key")

        return AuthResult.ok(identity=f"api_key:{api_key[:8]}…")


class OAuth2Auth:
    """Validate a Bearer token against an OAuth2 provider.

    Two validation strategies:
      - "userinfo":  GET /userinfo with Bearer token (Google, Auth0, etc.)
      - "introspect": POST /introspect with client credentials (RFC 7662)

    Caches successful validations for ``cache_ttl`` seconds to reduce
    round-trips to the identity provider.
    """

    def __init__(
        self,
        *,
        provider_url: str,
        strategy: str = "userinfo",
        client_id: str = "",
        client_secret: str = "",
        cache_ttl: int = 300,
        required_scope: str = "",
        required_audience: str = "",
    ) -> None:
        self._provider_url = provider_url.rstrip("/")
        self._strategy = strategy
        self._client_id = client_id
        self._client_secret = client_secret
        self._cache_ttl = cache_ttl
        self._required_scope = required_scope
        self._required_audience = required_audience

        # Simple in-memory cache: token -> (identity, expires_at)
        self._cache: dict[str, tuple[str, float]] = {}

    def check(self, headers: dict[str, str]) -> AuthResult:
        auth_header = headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return AuthResult.fail(401, "Unauthorized: Bearer token required for OAuth2")

        token = auth_header[len("Bearer "):]

        # Check cache first
        cached = self._cache.get(token)
        if cached is not None:
            identity, expires_at = cached
            if time.monotonic() < expires_at:
                return AuthResult.ok(identity=identity)
            # Expired — remove
            del self._cache[token]

        # Validate with provider
        try:
            if self._strategy == "introspect":
                return self._introspect(token)
            else:
                return self._userinfo(token)
        except URLError as exc:
            return AuthResult.fail(502, f"OAuth2 provider unreachable: {exc.reason}")
        except Exception as exc:
            return AuthResult.fail(502, f"OAuth2 validation error: {exc}")

    def _userinfo(self, token: str) -> AuthResult:
        """Validate via GET /userinfo (common for OIDC providers)."""
        url = f"{self._provider_url}/userinfo"
        req = Request(url, headers={"Authorization": f"Bearer {token}"})
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return AuthResult.fail(401, "OAuth2 token rejected by provider")
            data: dict[str, Any] = json.loads(resp.read())

        return self._validate_claims(token, data)

    def _introspect(self, token: str) -> AuthResult:
        """Validate via POST /introspect (RFC 7662)."""
        import base64

        url = f"{self._provider_url}/introspect"
        body = f"token={token}".encode()
        headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self._client_id and self._client_secret:
            creds = base64.b64encode(
                f"{self._client_id}:{self._client_secret}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {creds}"

        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=10) as resp:
            data: dict[str, Any] = json.loads(resp.read())

        if not data.get("active", False):
            return AuthResult.fail(401, "OAuth2 token is not active")

        return self._validate_claims(token, data)

    def _validate_claims(self, token: str, claims: dict[str, Any]) -> AuthResult:
        """Check required scope/audience and cache the result."""
        # Scope check (space-separated per RFC)
        if self._required_scope:
            token_scopes = set((claims.get("scope", "") or "").split())
            required = set(self._required_scope.split())
            if not required.issubset(token_scopes):
                missing = required - token_scopes
                return AuthResult.fail(403, f"Forbidden: missing scope(s): {', '.join(sorted(missing))}")

        # Audience check
        if self._required_audience:
            audiences = claims.get("aud", "")
            if isinstance(audiences, str):
                audiences = [audiences]
            if self._required_audience not in audiences:
                return AuthResult.fail(403, "Forbidden: invalid audience")

        identity = claims.get("sub") or claims.get("email") or claims.get("client_id") or "oauth2:user"

        # Cache the successful result
        self._cache[token] = (identity, time.monotonic() + self._cache_ttl)

        return AuthResult.ok(identity=f"oauth2:{identity}")


class MultiAuth:
    """Try multiple auth backends in order; first success wins.

    If no backend is configured, all requests are allowed (open mode).
    """

    def __init__(self, backends: list[BearerAuth | ApiKeyAuth | OAuth2Auth] | None = None) -> None:
        self._backends = backends or []

    @property
    def is_enabled(self) -> bool:
        return len(self._backends) > 0

    def check(self, headers: dict[str, str]) -> AuthResult:
        if not self._backends:
            return AuthResult.ok(identity="open")

        last_result: AuthResult | None = None
        for backend in self._backends:
            result = backend.check(headers)
            if result.success:
                return result
            # Remember the "best" failure — prefer 403 over 401 if any
            # backend confirmed credentials were present but wrong
            if last_result is None or result.error_status > last_result.error_status:
                last_result = result

        # Return the most specific failure
        return last_result or AuthResult.fail(401, "Unauthorized")


def build_auth_from_env() -> MultiAuth:
    """Build a MultiAuth instance from environment variables.

    Environment variables:
      ENVAULT_API_TOKEN    — Bearer token (legacy, existing)
      ENVAULT_API_KEY      — API key(s) for X-API-Key header auth
      ENVAULT_OAUTH2_URL   — OAuth2 provider base URL
      ENVAULT_OAUTH2_STRATEGY — "userinfo" (default) or "introspect"
      ENVAULT_OAUTH2_CLIENT_ID     — OAuth2 client ID (introspect)
      ENVAULT_OAUTH2_CLIENT_SECRET — OAuth2 client secret (introspect)
      ENVAULT_OAUTH2_SCOPE   — Required scope(s), space-separated
      ENVAULT_OAUTH2_AUDIENCE — Required audience
    """
    backends: list[BearerAuth | ApiKeyAuth | OAuth2Auth] = []

    # Bearer token (existing)
    bearer_token = os.environ.get("ENVAULT_API_TOKEN", "")
    if bearer_token:
        backends.append(BearerAuth(bearer_token))

    # API key
    api_key = os.environ.get("ENVAULT_API_KEY", "")
    if api_key:
        backends.append(ApiKeyAuth(api_key))

    # OAuth2
    oauth_url = os.environ.get("ENVAULT_OAUTH2_URL", "")
    if oauth_url:
        backends.append(
            OAuth2Auth(
                provider_url=oauth_url,
                strategy=os.environ.get("ENVAULT_OAUTH2_STRATEGY", "userinfo"),
                client_id=os.environ.get("ENVAULT_OAUTH2_CLIENT_ID", ""),
                client_secret=os.environ.get("ENVAULT_OAUTH2_CLIENT_SECRET", ""),
                required_scope=os.environ.get("ENVAULT_OAUTH2_SCOPE", ""),
                required_audience=os.environ.get("ENVAULT_OAUTH2_AUDIENCE", ""),
            )
        )

    return MultiAuth(backends)
