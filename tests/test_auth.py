from __future__ import annotations

import json

from envault.auth import OAuth2Auth


def test_oauth2_introspection_url_encodes_reserved_token_characters(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"active": True, "sub": "synthetic-user"}).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("envault.auth.urlopen", fake_urlopen)

    result = OAuth2Auth(provider_url="https://identity.example", strategy="introspect").check(
        {"Authorization": "Bearer token+with&reserved=value"}
    )

    assert result.success
    request = captured["request"]
    assert request.data == b"token=token%2Bwith%26reserved%3Dvalue"
    assert captured["timeout"] == 10
