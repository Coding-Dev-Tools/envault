"""Tests for Envault encrypt/decrypt with common secret formats.

Covers: multiline SSH keys, base64-encoded values, JSON blobs, unicode content.
Issue: COM-238
"""

import base64
from envault.cli import app
from envault.encrypt import decrypt_env, encrypt_env, is_encrypted
from typer.testing import CliRunner

# ── Test Data ──────────────────────────────────────────────────────────────

SAMPLE_RSA_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAACmFlczI1Ni1jdHIAAAAAbWFzazo1
MTIAAAASCgIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eH2hp
aGlqa2prbG1ub3BxcnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouM
jY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqsrO0tba3uLm6
eri4vL2+wcXGy8vNz9DS0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp
6uvs7e7v8PHy8/T19vf4+fr7/P3+/w==
-----END OPENSSH PRIVATE KEY-----"""

SAMPLE_RSA_PUBLIC_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7Vd3j9OTDXHvQ user@host"

SAMPLE_EC_PRIVATE_KEY = """-----BEGIN EC PRIVATE KEY-----
MHQCAQEEIOBwcG8eZ+YXqPp5TI5N0FYQcNQ7T5fL3qV3r+7KcnFSoAoGCCqGSM49
AwEHoUQDQgAE5W2gw9Y6bM5xQ5Y9J9Z6y5F0Z8Y8K7L4m3N2pR1T8V9A6B3C5D7
E9F0G2H4I6J8K0L2M4N6O8P0Q2R4S6T8U0V2W4X6Y8Z0A2B4C6D8E0F2G4H6I8J0
-----END EC PRIVATE KEY-----"""

SAMPLE_JSON_BLOB_SINGLE = """{"database_url":"postgresql://user:pass@db.example.com:5432/prod","redis_url":"redis://redis.example.com:6379/0","debug":false}"""

SAMPLE_JSON_BLOB_NESTED = """{
  "aws": {
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "region": "us-east-1"
  },
  "stripe": {
    "api_key": "sk_live_abc123def456",
    "webhook_secret": "whsec_abc123"
  }
}"""

SAMPLE_BASE64_VALUE = base64.b64encode(b"This is some binary data that was base64 encoded for a secret value!").decode()

SAMPLE_BASE64URL_VALUE = base64.urlsafe_b64encode(b"Binary data with special chars: \x00\x01\x02\xff").decode()

SAMPLE_UNICODE_CONTENT = """DATABASE_URL=postgresql://müller:p@sswörd@db.exämple.com:5432/pröd
API_KEY=日本語テストキー123
CHINESE_KEY=中文密钥值
EMOJI_KEY=🔑_secret_value_🛡️
RUSSIAN_KEY=Пароль_для_доступа
ARABIC_KEY=مفتاح_سري
MIXED_KEY=Café_ñaño_über_straße
THAI_KEY=คีย์ลับ_รหัสผ่าน"""

SAMPLE_DOCKER_CONFIG = """{
  "auths": {
    "https://registry.example.com": {
      "username": "deploy",
      "password": "s3cretP@ss!",
      "auth": "ZGVwbG95OnMzY3JldFBAc3Mh"
    }
  }
}"""

SAMPLE_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

SAMPLE_PEM_CERT = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL3wg3MQMZ6MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMjQwMTAxMDAwMDAwWhcNMjUwMTAxMDAwMDAwWjBF
MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50
ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB
CgKCAQEAyL7sM7O8YXpN9m5Z1vKQ0rR4jG3hWL2k8pNsQf6Y0wT5YqJ3v8xH2b1A
-----END CERTIFICATE-----"""

SAMPLE_MULTILINE_ENV = """SSH_PRIVATE_KEY="-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAACmFlczI1Ni1jdHIAAAAAbWFzazo1
-----END OPENSSH PRIVATE KEY-----"
SSH_PUBLIC_KEY=ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7Vd3 user@host
DB_PASSWORD=simple_password
API_KEY_BASE64={base64_value}
JSON_CONFIG={json_blob}
DOCKER_AUTH={docker_config}
JWT_SECRET={jwt_token}
PEM_CERT="-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL3wg3MQMZ6MA0GCSqGSIb3DQEBCwUA
-----END CERTIFICATE-----"
UNICODE_VAR=Café_ñaño_über_straße
EMOJI_VAR=🔑_value_🛡️
""".format(
    base64_value=SAMPLE_BASE64_VALUE,
    json_blob=SAMPLE_JSON_BLOB_SINGLE.replace('"', '\\"'),
    docker_config=SAMPLE_DOCKER_CONFIG.replace('"', '\\"').replace("\n", ""),
    jwt_token=SAMPLE_JWT_TOKEN,
)


PASSWORD = "test-password-for-qa-!@#$%"


# ── Direct API Tests (encrypt_env / decrypt_env) ──────────────────────────


class TestEncryptDecryptSSHKek:
    """Encrypt/decrypt roundtrip with SSH key content."""

    def test_rsa_private_key_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"SSH_KEY={SAMPLE_RSA_PRIVATE_KEY}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        assert encrypted.exists()
        assert is_encrypted(encrypted)

        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_rsa_public_key_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"SSH_PUBLIC_KEY={SAMPLE_RSA_PUBLIC_KEY}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_ec_private_key_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"EC_KEY={SAMPLE_EC_PRIVATE_KEY}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content


class TestEncryptDecryptBase64:
    """Encrypt/decrypt roundtrip with base64-encoded values."""

    def test_base64_standard_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"SECRET_B64={SAMPLE_BASE64_VALUE}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_base64url_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"SECRET_B64URL={SAMPLE_BASE64URL_VALUE}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_base64_with_padding_roundtrip(self, tmp_path):
        """Base64 with = padding characters."""
        val = "dGVzdA=="  # base64 of "test"
        env_file = tmp_path / ".env"
        content = f"PADDED_B64={val}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content


class TestEncryptDecryptJSON:
    """Encrypt/decrypt roundtrip with JSON blob content."""

    def test_json_single_line_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"CONFIG={SAMPLE_JSON_BLOB_SINGLE}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_json_nested_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"CREDENTIALS={SAMPLE_JSON_BLOB_NESTED}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_docker_config_json_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"DOCKER_CONFIG={SAMPLE_DOCKER_CONFIG}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content


class TestEncryptDecryptUnicode:
    """Encrypt/decrypt roundtrip with unicode content."""

    def test_unicode_multiline_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(SAMPLE_UNICODE_CONTENT, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == SAMPLE_UNICODE_CONTENT

    def test_cjk_characters_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = "API_KEY=日本語テストキー123\nCHINESE=中文密钥值\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_emoji_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = "KEY=🔑_value_🛡️\nFLAG=🏳️‍🌈_secret\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_rtl_scripts_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = "ARABIC=مفتاح_سري\nHEBREW=סוד_מפתח\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_mixed_unicode_ascii_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = "KEY=Café_ñaño_über_straße\nPLAIN=ascii_value\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content


class TestEncryptDecryptJWT:
    """Encrypt/decrypt roundtrip with JWT tokens."""

    def test_jwt_token_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"JWT_TOKEN={SAMPLE_JWT_TOKEN}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content


class TestEncryptDecryptPEM:
    """Encrypt/decrypt roundtrip with PEM certificates."""

    def test_pem_cert_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        content = f"TLS_CERT={SAMPLE_PEM_CERT}\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content


class TestEncryptDecryptComplexMixed:
    """Encrypt/decrypt with mixed complex content."""

    def test_multiline_mixed_env_roundtrip(self, tmp_path):
        """Full .env with multiline SSH keys, JSON, unicode, base64."""
        env_file = tmp_path / ".env"
        content = SAMPLE_MULTILINE_ENV
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content

    def test_binary_like_content_roundtrip(self, tmp_path):
        """Content with special characters that could confuse encoding."""
        env_file = tmp_path / ".env"
        # Newlines, tabs, special chars
        content = "KEY1=value with spaces\nKEY2=value\twith\ttabs\nKEY3=value_with_=!@#$%^&*()\n"
        env_file.write_text(content, encoding="utf-8")

        encrypted = encrypt_env(env_file, password=PASSWORD)
        decrypted = decrypt_env(encrypted, output_path=tmp_path / ".env.restored", password=PASSWORD)
        assert decrypted.read_text(encoding="utf-8") == content


# ── CLI Roundtrip Tests ───────────────────────────────────────────────────


class TestCLIEncryptDecryptSecretFormats:
    """CLI encrypt/decrypt roundtrip tests for all secret formats."""

    def test_cli_ssh_key_roundtrip(self, tmp_path):
        runner = CliRunner()
        env_file = tmp_path / ".env"
        content = f"SSH_KEY={SAMPLE_RSA_PRIVATE_KEY}\n"
        env_file.write_text(content, encoding="utf-8")
        encrypted = tmp_path / ".env.locked"

        result_enc = runner.invoke(app, ["encrypt", str(env_file), "--output", str(encrypted), "--password", PASSWORD])
        assert result_enc.exit_code == 0, f"Encrypt failed: {result_enc.output}"

        decrypted = tmp_path / ".env.restored"
        result_dec = runner.invoke(app, ["decrypt", str(encrypted), "--output", str(decrypted), "--password", PASSWORD])
        assert result_dec.exit_code == 0, f"Decrypt failed: {result_dec.output}"
        assert decrypted.read_text(encoding="utf-8") == content

    def test_cli_json_blob_roundtrip(self, tmp_path):
        runner = CliRunner()
        env_file = tmp_path / ".env"
        content = f"CONFIG={SAMPLE_JSON_BLOB_SINGLE}\n"
        env_file.write_text(content, encoding="utf-8")
        encrypted = tmp_path / ".env.locked"

        result_enc = runner.invoke(app, ["encrypt", str(env_file), "--output", str(encrypted), "--password", PASSWORD])
        assert result_enc.exit_code == 0, f"Encrypt failed: {result_enc.output}"

        decrypted = tmp_path / ".env.restored"
        result_dec = runner.invoke(app, ["decrypt", str(encrypted), "--output", str(decrypted), "--password", PASSWORD])
        assert result_dec.exit_code == 0, f"Decrypt failed: {result_dec.output}"
        assert decrypted.read_text(encoding="utf-8") == content

    def test_cli_unicode_roundtrip(self, tmp_path):
        runner = CliRunner()
        env_file = tmp_path / ".env"
        env_file.write_text(SAMPLE_UNICODE_CONTENT, encoding="utf-8")
        encrypted = tmp_path / ".env.locked"

        result_enc = runner.invoke(app, ["encrypt", str(env_file), "--output", str(encrypted), "--password", PASSWORD])
        assert result_enc.exit_code == 0, f"Encrypt failed: {result_enc.output}"

        decrypted = tmp_path / ".env.restored"
        result_dec = runner.invoke(app, ["decrypt", str(encrypted), "--output", str(decrypted), "--password", PASSWORD])
        assert result_dec.exit_code == 0, f"Decrypt failed: {result_dec.output}"
        assert decrypted.read_text(encoding="utf-8") == SAMPLE_UNICODE_CONTENT

    def test_cli_base64_roundtrip(self, tmp_path):
        runner = CliRunner()
        env_file = tmp_path / ".env"
        content = f"SECRET_B64={SAMPLE_BASE64_VALUE}\n"
        env_file.write_text(content, encoding="utf-8")
        encrypted = tmp_path / ".env.locked"

        result_enc = runner.invoke(app, ["encrypt", str(env_file), "--output", str(encrypted), "--password", PASSWORD])
        assert result_enc.exit_code == 0, f"Encrypt failed: {result_enc.output}"

        decrypted = tmp_path / ".env.restored"
        result_dec = runner.invoke(app, ["decrypt", str(encrypted), "--output", str(decrypted), "--password", PASSWORD])
        assert result_dec.exit_code == 0, f"Decrypt failed: {result_dec.output}"
        assert decrypted.read_text(encoding="utf-8") == content

    def test_cli_mixed_complex_roundtrip(self, tmp_path):
        runner = CliRunner()
        env_file = tmp_path / ".env"
        env_file.write_text(SAMPLE_MULTILINE_ENV, encoding="utf-8")
        encrypted = tmp_path / ".env.locked"

        result_enc = runner.invoke(app, ["encrypt", str(env_file), "--output", str(encrypted), "--password", PASSWORD])
        assert result_enc.exit_code == 0, f"Encrypt failed: {result_enc.output}"

        decrypted = tmp_path / ".env.restored"
        result_dec = runner.invoke(app, ["decrypt", str(encrypted), "--output", str(decrypted), "--password", PASSWORD])
        assert result_dec.exit_code == 0, f"Decrypt failed: {result_dec.output}"
        assert decrypted.read_text(encoding="utf-8") == SAMPLE_MULTILINE_ENV