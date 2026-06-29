"""Comprehensive encrypt/decrypt tests for common secret formats.

Tests: multiline SSH keys, base64, JSON blobs, unicode, PEM certs,
       Docker configs, .env with quotes, mixed line endings, large files.
"""

import json
import os
from envault.encrypt import decrypt_env, encrypt_env

PASSWORD = "test-password-for-qa"


# ── Multiline SSH Keys ──────────────────────────────────────────────────────

SSH_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACDR3xm6L8mb8i5Uy9B5Ym3GqF5xN2xX8R7vKJ4dT2qYQAAAJj7H9J1+x/S
dQAAAAtzc2gtZWQyNTUxOQAAACDR3xm6L8mb8i5Uy9B5Ym3GqF5xN2xX8R7vKJ4dT2qYQ
AAAEC3mZ8x7R5vNKJ9Q2m0p5F7V8t3J6lK4hY1Df0vN2xN7NHfGbovyZvyLlTL0Hlibcao
XnE3bFfxHu8onh1PaphAAAAE2V4YW1wbGVAZXhhbXBsZS5jb20BAgMEBQ==
-----END OPENSSH PRIVATE KEY-----"""

SSH_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINHfGbovyZvyLlTL0HlibcaoXnE3bFfxHu8onh1Paph example@example.com"

RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGyE8QJ3kVjJJBq0m58h8Y2f
vN3eQ7vD7vJ8R3mK2x1L9W5Q8d3R5vN7K8h8Y2fJ3mK6x1L9W5Q8d3R5vN7K8h
8Y2fJ3mK6x1L9W5Q8d3R5vN7K8h8Y2fJ3mK6x1L9W5Q8d3R5vN7K8h8Y2fJ3mK
-----END RSA PRIVATE KEY-----"""


def test_encrypt_decrypt_ssh_private_key(tmp_path):
    """Multiline SSH private key roundtrips correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"SSH_PRIVATE_KEY={SSH_PRIVATE_KEY}\nOTHER=plain\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "BEGIN OPENSSH PRIVATE KEY" in content
    assert "END OPENSSH PRIVATE KEY" in content
    assert "OTHER=plain" in content
    # Ensure the full key is preserved
    assert SSH_PRIVATE_KEY in content


def test_encrypt_decrypt_ssh_public_key(tmp_path):
    """Single-line SSH public key roundtrips correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"SSH_PUBLIC_KEY={SSH_PUBLIC_KEY}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert SSH_PUBLIC_KEY in content


def test_encrypt_decrypt_rsa_key(tmp_path):
    """RSA private key with header/footer roundtrips."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"RSA_KEY={RSA_PRIVATE_KEY}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "BEGIN RSA PRIVATE KEY" in content
    assert "END RSA PRIVATE KEY" in content


# ── Base64 Encoded Content ──────────────────────────────────────────────────


def test_encrypt_decrypt_base64_value(tmp_path):
    """Base64-encoded secret value roundtrips."""
    import base64

    raw_secret = b"super_secret_binary_data\x00\x01\x02\xff\xfe"
    b64_value = base64.b64encode(raw_secret).decode()

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require\nSECRET_B64={b64_value}\n"
    )

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert b64_value in content


def test_encrypt_decrypt_base64_multiline(tmp_path):
    """Multiline base64 (like PEM without headers) roundtrips."""
    import base64

    raw = os.urandom(256)
    b64_multiline = base64.encodebytes(raw).decode().strip()

    env_file = tmp_path / ".env"
    content = f"CERT_B64={b64_multiline}\n"
    env_file.write_text(content)

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    result = decrypted.read_text(encoding="utf-8")
    assert b64_multiline in result


# ── JSON Blobs ──────────────────────────────────────────────────────────────


def test_encrypt_decrypt_json_blob_single_line(tmp_path):
    """Single-line JSON blob as env value."""
    json_blob = json.dumps(
        {
            "host": "db.example.com",
            "port": 5432,
            "ssl": True,
            "options": {"timeout": 30},
        }
    )
    env_file = tmp_path / ".env"
    env_file.write_text(f"DB_CONFIG={json_blob}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert json_blob in content


def test_encrypt_decrypt_json_blob_multiline(tmp_path):
    """Multiline pretty-printed JSON as env value."""
    json_blob = json.dumps(
        {
            "version": "3",
            "services": {
                "web": {"image": "nginx:latest", "ports": ["80:80"]},
                "db": {
                    "image": "postgres:15",
                    "environment": {"POSTGRES_PASSWORD": "s3cret"},
                },
            },
        },
        indent=2,
    )

    env_file = tmp_path / ".env"
    env_file.write_text(f"COMPOSE_CONFIG={json_blob}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert json_blob in content


def test_encrypt_decrypt_json_with_special_chars(tmp_path):
    """JSON with quotes, backslashes, and special characters."""
    json_blob = json.dumps(
        {"key": 'value with "quotes" and \\backslashes\\', "path": "C:\\Users\\test"}
    )

    env_file = tmp_path / ".env"
    env_file.write_text(f"SPECIAL_JSON={json_blob}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert json_blob in content


# ── Unicode Content ─────────────────────────────────────────────────────────


def test_encrypt_decrypt_unicode_cjk(tmp_path):
    """CJK characters in env values."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=日本語アプリ\nGREETING=こんにちは世界\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "日本語アプリ" in content
    assert "こんにちは世界" in content


def test_encrypt_decrypt_unicode_emoji(tmp_path):
    """Emoji in env values."""
    env_file = tmp_path / ".env"
    env_file.write_text("STATUS=🚀 ready\nLOGO=🔷🔷🔷\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "🚀 ready" in content
    assert "🔷🔷🔷" in content


def test_encrypt_decrypt_unicode_mixed_scripts(tmp_path):
    """Mixed scripts (Latin, Cyrillic, Arabic, Thai) in env values."""
    env_file = tmp_path / ".env"
    env_file.write_text("RUSSIAN=Привет мир\nARABIC=مرحبا بالعالم\nTHAI=สวัสดีชาวโลก\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "Привет мир" in content
    assert "مرحبا بالعالم" in content
    assert "สวัสดีชาวโลก" in content


def test_encrypt_decrypt_unicode_zero_width(tmp_path):
    """Zero-width characters and combining diacritics."""
    env_file = tmp_path / ".env"
    # Zero-width joiner, zero-width space, combining characters
    env_file.write_text(
        "ZWJ=test\u200dvalue\nZW_SPACE=hello\u200bworld\nCOMBINED=cafe\u0301\n"
    )

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "test\u200dvalue" in content
    assert "hello\u200bworld" in content
    assert "cafe\u0301" in content


# ── Edge Cases ──────────────────────────────────────────────────────────────


def test_encrypt_decrypt_pem_certificate(tmp_path):
    """Full PEM certificate with headers."""
    pem_cert = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRKN7MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMjQwMTAxMDAwMDAwWhcNMjUwMTAxMDAwMDAwWjBF
-----END CERTIFICATE-----"""

    env_file = tmp_path / ".env"
    env_file.write_text(f"SSL_CERT={pem_cert}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "BEGIN CERTIFICATE" in content
    assert "END CERTIFICATE" in content


def test_encrypt_decrypt_docker_config_json(tmp_path):
    """Docker-style config.json with auth blobs."""
    docker_config = json.dumps(
        {
            "auths": {
                "https://index.docker.io/v1/": {"auth": "dXNlcm5hbWU6cGFzc3dvcmQ="}
            },
            "credsStore": "desktop",
        }
    )

    env_file = tmp_path / ".env"
    env_file.write_text(f"DOCKER_CONFIG={docker_config}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "dXNlcm5hbWU6cGFzc3dvcmQ=" in content


def test_encrypt_decrypt_env_with_quotes(tmp_path):
    """Env values containing various quote styles."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MSG=\"Hello World\"\nPATH_VAR='C:\\Users\\test'\nSHELL_VAR=`echo hi`\n"
    )

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert '"Hello World"' in content
    assert "'C:\\Users\\test'" in content
    assert "`echo hi`" in content


def test_encrypt_decrypt_newlines_in_values(tmp_path):
    """Values containing literal backslash-n sequences."""
    env_file = tmp_path / ".env"
    env_file.write_text("MULTILINE=key1\\nkey2\\nkey3\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "key1\\nkey2\\nkey3" in content


def test_encrypt_decrypt_mixed_line_endings(tmp_path):
    """File with mixed CRLF/LF line endings."""
    env_file = tmp_path / ".env"
    content = "KEY1=value1\r\nKEY2=value2\nKEY3=value3\r\n"
    env_file.write_bytes(content.encode("utf-8"))

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    # After roundtrip, the raw bytes should match (encrypt stores as bytes)
    result = decrypted.read_bytes()
    assert b"KEY1=value1" in result
    assert b"KEY2=value2" in result
    assert b"KEY3=value3" in result


def test_encrypt_decrypt_equals_in_value(tmp_path):
    """Values containing = signs (common in base64, connection strings)."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CONN_STRING=Host=db;Port=5432;User=admin;Password=s3cret==\nB64_PAD=SGVsbG8gV29ybGQ=\n"
    )

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "Host=db;Port=5432;User=admin;Password=s3cret==" in content
    assert "SGVsbG8gV29ybGQ=" in content


def test_encrypt_decrypt_large_file(tmp_path):
    """Large .env file (200 keys) roundtrips correctly."""
    lines = []
    for i in range(200):
        lines.append(f"KEY_{i:04d}=value_{i}_{'x' * 50}\n")
    content = "".join(lines)

    env_file = tmp_path / ".env"
    env_file.write_text(content)

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    result = decrypted.read_text(encoding="utf-8")
    assert "KEY_0000=" in result
    assert "KEY_0199=" in result
    # Full roundtrip
    assert result == content


def test_encrypt_decrypt_empty_lines_and_comments(tmp_path):
    """File with comments, empty lines, and blank-key edge cases."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# This is a comment\n\nKEY=value\n# Another comment\n\nOTHER=stuff\n"
    )

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "# This is a comment" in content
    assert "KEY=value" in content
    assert "# Another comment" in content
    assert "OTHER=stuff" in content


def test_encrypt_decrypt_whitespace_values(tmp_path):
    """Values with leading/trailing whitespace and tabs."""
    env_file = tmp_path / ".env"
    env_file.write_text("SPACES=  leading and trailing  \nTABS=\tvalue\t\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    # The file is read as text and roundtripped, so whitespace should be preserved
    assert "  leading and trailing  " in content
    assert "\tvalue\t" in content


def test_encrypt_decrypt_binary_like_values(tmp_path):
    """Values that look like binary/hex (common for tokens, API keys)."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "API_KEY=sk-ant-3a5f8b2c9d1e4f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0\nHEX_SECRET=deadbeef0102030405060708\nJWT=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig\n"
    )

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert (
        "sk-ant-3a5f8b2c9d1e4f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0"
        in content
    )
    assert "deadbeef0102030405060708" in content
    assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" in content


def test_encrypt_decrypt_yaml_blob(tmp_path):
    """YAML blob as env value (k8s config style)."""
    yaml_blob = """apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
data:
  key1: value1
  key2: value2"""

    env_file = tmp_path / ".env"
    env_file.write_text(f"K8S_CONFIG={yaml_blob}\n")

    encrypted = encrypt_env(env_file, password=PASSWORD)
    decrypted = decrypt_env(
        encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD
    )

    content = decrypted.read_text(encoding="utf-8")
    assert "apiVersion: v1" in content
    assert "kind: ConfigMap" in content
