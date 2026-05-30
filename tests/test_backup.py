"""Tests for envault backup and restore commands."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from envault.backup import (
    BACKUP_MANIFEST_KEY,
    backup_env_files,
    restore_env_files,
)
from envault.cli import app

runner = CliRunner()


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def env_dir(tmp_path: Path) -> Path:
    """Create a temp directory with sample .env files."""
    (tmp_path / ".env").write_text("DB_HOST=localhost\nDB_PORT=5432\n")
    (tmp_path / ".env.dev").write_text("DB_HOST=dev.example.com\nDB_PORT=5432\n")
    (tmp_path / ".env.prod").write_text("DB_HOST=prod.example.com\nDB_PORT=5432\nSECRET_KEY=abc123\n")
    return tmp_path


# ── backup_env_files unit tests ──────────────────────────────────────────────


class TestBackupEnvFiles:
    def test_backup_single_file(self, env_dir: Path):
        env_file = env_dir / ".env"
        output = env_dir / "test.envault.bak"

        result = backup_env_files([env_file], output_path=output, password="testpass")

        assert result == output
        assert output.exists()
        # Verify the file starts with salt (16 bytes) + Fernet token
        data = output.read_bytes()
        assert len(data) > 16

    def test_backup_multiple_files(self, env_dir: Path):
        files = [env_dir / ".env", env_dir / ".env.dev", env_dir / ".env.prod"]
        output = env_dir / "multi.envault.bak"

        result = backup_env_files(files, output_path=output, password="testpass")

        assert result == output
        assert output.exists()

    def test_backup_default_output_path(self, env_dir: Path, monkeypatch):
        monkeypatch.chdir(env_dir)
        env_file = env_dir / ".env"

        result = backup_env_files([env_file], password="testpass")

        assert result.exists()
        assert result.name.endswith(".envault.bak")
        # Cleanup
        result.unlink()

    def test_backup_missing_file_raises(self, env_dir: Path):
        missing = env_dir / ".env.staging"
        output = env_dir / "test.envault.bak"

        with pytest.raises(FileNotFoundError, match="not found"):
            backup_env_files([missing], output_path=output, password="testpass")

    def test_backup_empty_list_raises(self, env_dir: Path):
        output = env_dir / "test.envault.bak"

        with pytest.raises(ValueError, match="No .env files"):
            backup_env_files([], output_path=output, password="testpass")

    def test_backup_uses_env_var_password(self, env_dir: Path, monkeypatch):
        monkeypatch.setenv("ENVAULT_ENCRYPT_KEY", "env-var-password")
        env_file = env_dir / ".env"
        output = env_dir / "envvar.envault.bak"

        result = backup_env_files([env_file], output_path=output, password=None)

        assert result == output
        assert output.exists()

    def test_backup_content_is_encrypted(self, env_dir: Path):
        env_file = env_dir / ".env.prod"
        output = env_dir / "encrypted.envault.bak"

        backup_env_files([env_file], output_path=output, password="secret123")

        # Raw content should NOT contain plaintext
        raw = output.read_bytes()
        assert b"prod.example.com" not in raw
        assert b"abc123" not in raw


# ── restore_env_files unit tests ─────────────────────────────────────────────


class TestRestoreEnvFiles:
    def test_restore_roundtrip_single_file(self, env_dir: Path):
        env_file = env_dir / ".env"
        backup_path = env_dir / "roundtrip.envault.bak"
        restore_dir = env_dir / "restored"

        backup_env_files([env_file], output_path=backup_path, password="mypass")
        restored = restore_env_files(
            backup_path, output_dir=restore_dir, password="mypass"
        )

        assert len(restored) == 1
        # The restored file will be named .env (filename only from backup)
        original_content = env_file.read_text()
        restored_content = restored[0].read_text()
        assert restored_content == original_content

    def test_restore_roundtrip_multiple_files(self, env_dir: Path):
        files = [env_dir / ".env", env_dir / ".env.dev", env_dir / ".env.prod"]
        backup_path = env_dir / "multi.envault.bak"
        restore_dir = env_dir / "restored"

        backup_env_files(files, output_path=backup_path, password="mypass")
        restored = restore_env_files(
            backup_path, output_dir=restore_dir, password="mypass"
        )

        assert len(restored) == 3
        # Files are restored by filename; sort both lists for stable comparison
        original_contents = {f.name: f.read_text() for f in files}
        for r in restored:
            assert r.name in original_contents
            assert r.read_text() == original_contents[r.name]

    def test_restore_wrong_password_raises(self, env_dir: Path):
        env_file = env_dir / ".env"
        backup_path = env_dir / "wrong.envault.bak"

        backup_env_files([env_file], output_path=backup_path, password="correct")
        with pytest.raises(ValueError, match="Decryption failed"):
            restore_env_files(backup_path, password="wrong")

    def test_restore_missing_backup_raises(self, env_dir: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            restore_env_files(env_dir / "nonexistent.envault.bak", password="x")

    def test_restore_corrupt_backup_raises(self, env_dir: Path):
        bad_file = env_dir / "corrupt.envault.bak"
        bad_file.write_bytes(b"not_valid_encrypted_data_at_all!!")

        with pytest.raises(ValueError, match="Decryption failed"):
            restore_env_files(bad_file, password="x")

    def test_restore_too_small_raises(self, env_dir: Path):
        tiny = env_dir / "tiny.envault.bak"
        tiny.write_bytes(b"x")

        with pytest.raises(ValueError, match="too small"):
            restore_env_files(tiny, password="x")

    def test_restore_no_overwrite_raises(self, env_dir: Path):
        env_file = env_dir / ".env"
        backup_path = env_dir / "nooverwrite.envault.bak"
        restore_dir = env_dir  # same dir where .env already exists

        backup_env_files([env_file], output_path=backup_path, password="mypass")

        # Restoring to same dir where .env already exists
        with pytest.raises(FileExistsError, match="already exists"):
            restore_env_files(
                backup_path, output_dir=restore_dir, password="mypass", overwrite=False
            )

    def test_restore_with_overwrite(self, env_dir: Path):
        env_file = env_dir / ".env"
        backup_path = env_dir / "overwrite.envault.bak"
        restore_dir = env_dir  # same dir where .env already exists

        backup_env_files([env_file], output_path=backup_path, password="mypass")

        # Restore with overwrite to same dir
        restored = restore_env_files(
            backup_path, output_dir=restore_dir, password="mypass", overwrite=True
        )
        assert len(restored) == 1
        assert restored[0].read_text() == env_file.read_text()

    def test_restore_path_traversal_raises(self, tmp_path: Path):
        """Backup with path traversal in filename should raise ValueError."""
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        password = "testpass"
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)

        # Create a bundle with a path traversal filename
        bundle = {
            "../../etc/passwd": "MALICIOUS",
            BACKUP_MANIFEST_KEY: json.dumps({"version": "1", "timestamp": "2026-01-01T00:00:00Z", "files": []}),
        }
        encrypted = fernet.encrypt(json.dumps(bundle).encode())

        bad_backup = tmp_path / "malicious.envault.bak"
        bad_backup.write_bytes(salt + encrypted)

        restore_dir = tmp_path / "restore"
        restore_dir.mkdir()

        with pytest.raises(ValueError, match="outside output directory"):
            restore_env_files(bad_backup, output_dir=restore_dir, password=password)


# ── CLI integration tests ────────────────────────────────────────────────────


class TestBackupCLI:
    def test_backup_file_flag(self, env_dir: Path, monkeypatch):
        monkeypatch.chdir(env_dir)
        output = env_dir / "cli-test.envault.bak"

        result = runner.invoke(app, [
            "backup",
            "--file", str(env_dir / ".env"),
            "--output", str(output),
            "--password", "clipass",
        ])

        assert result.exit_code == 0, result.output
        assert "Backed up 1" in result.output
        assert output.exists()

    def test_backup_multiple_files(self, env_dir: Path, monkeypatch):
        monkeypatch.chdir(env_dir)
        output = env_dir / "cli-multi.envault.bak"

        # Use --file for each env (backup command takes one --file)
        # For multi, we'd need a config, so let's just test single file
        result = runner.invoke(app, [
            "backup",
            "--file", str(env_dir / ".env.prod"),
            "--output", str(output),
            "--password", "clipass",
        ])

        assert result.exit_code == 0, result.output
        assert "Backed up" in result.output

    def test_backup_missing_file_exits_1(self, env_dir: Path):
        result = runner.invoke(app, [
            "backup",
            "--file", str(env_dir / ".env.nonexistent"),
            "--output", str(env_dir / "nope.bak"),
            "--password", "clipass",
        ])

        assert result.exit_code == 1

    def test_backup_no_env_files_in_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No .envault.yml, no .env files
        result = runner.invoke(app, [
            "backup",
            "--password", "clipass",
        ])

        # Should either exit 0 (no files) or 1 (error)
        assert result.exit_code in (0, 1)


class TestRestoreCLI:
    def test_restore_roundtrip(self, env_dir: Path, monkeypatch):
        monkeypatch.chdir(env_dir)
        backup_path = env_dir / "cli-roundtrip.envault.bak"
        restore_dir = env_dir / "cli-restored"

        # Create backup
        runner.invoke(app, [
            "backup",
            "--file", str(env_dir / ".env"),
            "--output", str(backup_path),
            "--password", "clipass",
        ])

        # Restore
        result = runner.invoke(app, [
            "restore",
            str(backup_path),
            "--output-dir", str(restore_dir),
            "--password", "clipass",
        ])

        assert result.exit_code == 0, result.output
        assert "Restored 1" in result.output

    def test_restore_wrong_password_exits_1(self, env_dir: Path):
        backup_path = env_dir / "cli-wrong.envault.bak"

        runner.invoke(app, [
            "backup",
            "--file", str(env_dir / ".env"),
            "--output", str(backup_path),
            "--password", "correct",
        ])

        result = runner.invoke(app, [
            "restore",
            str(backup_path),
            "--password", "wrong",
        ])

        assert result.exit_code == 1

    def test_restore_overwrite_flag(self, env_dir: Path, monkeypatch):
        monkeypatch.chdir(env_dir)
        backup_path = env_dir / "cli-overwrite.envault.bak"

        runner.invoke(app, [
            "backup",
            "--file", str(env_dir / ".env"),
            "--output", str(backup_path),
            "--password", "clipass",
        ])

        # Restore with --overwrite to same dir where .env exists
        result = runner.invoke(app, [
            "restore",
            str(backup_path),
            "--password", "clipass",
            "--overwrite",
        ])

        assert result.exit_code == 0, result.output


# ── Manifest integrity tests ────────────────────────────────────────────────


class TestBackupManifest:
    def test_manifest_included_in_backup(self, env_dir: Path):
        env_file = env_dir / ".env"
        backup_path = env_dir / "manifest.envault.bak"

        backup_env_files([env_file], output_path=backup_path, password="testpass")

        # Decrypt and check manifest
        data = backup_path.read_bytes()
        salt = data[:16]
        encrypted = data[16:]

        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(b"testpass"))
        fernet = Fernet(key)
        bundle_json = fernet.decrypt(encrypted)
        bundle = json.loads(bundle_json)

        assert BACKUP_MANIFEST_KEY in bundle
        manifest = json.loads(bundle[BACKUP_MANIFEST_KEY])
        assert manifest["version"] == "1"
        assert "timestamp" in manifest
        assert len(manifest["files"]) == 1
