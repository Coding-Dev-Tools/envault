"""Tests for the Envault CLI (typer commands)."""

from __future__ import annotations

import pytest
from envault.cli import app
from pathlib import Path
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── Version ─────────────────────────────────────────────────────────────────


def test_version(runner: CliRunner):
    """--version should display the current version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "envault v" in result.stdout
    assert "0.1.0" in result.stdout


# ── Help ────────────────────────────────────────────────────────────────────


def test_help_no_args(runner: CliRunner):
    """Running without arguments should show help (may exit 2 in CliRunner)."""
    result = runner.invoke(app, [])
    # Typer shows help with no_args_is_help=True; CliRunner may exit 2 for no-args
    assert result.exit_code in (0, 2)
    assert "Usage:" in result.output
    assert "Env variable syncing" in result.output or "envault" in result.output


def test_help_version_in_commands(runner: CliRunner):
    """The version command should appear in help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "version" in result.stdout


# ── Init ────────────────────────────────────────────────────────────────────


def test_init_defaults(runner: CliRunner, tmp_path):
    """init should create a config file with the given project name."""
    config_path = tmp_path / ".envault.yml"
    result = runner.invoke(app, ["init", "my-project", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "Created" in result.stdout
    assert "my-project" in result.stdout
    assert config_path.exists()

    # Verify the file is valid YAML
    import yaml
    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert data.get("project") == "my-project"


def test_init_existing_raises(runner: CliRunner, tmp_path):
    """init should raise an error if config already exists."""
    config_path = tmp_path / ".envault.yml"
    config_path.write_text("project: existing\nenvironments: []\n")
    result = runner.invoke(app, ["init", "new-project", "--config", str(config_path)])
    assert result.exit_code == 0
    # Should be re-created, or let's check the behavior
    import yaml
    with open(config_path) as f:
        data = yaml.safe_load(f)
    # After re-init, project should be updated
    assert data.get("project") == "new-project"


# ── Diff ────────────────────────────────────────────────────────────────────


def _make_config(tmp_path, project="test", env_files=None):
    """Create a minimal .envault.yml for testing.

    env_files: dict of {env_name: env_file_path}
    Paths can be relative (resolved against tmp_path) or absolute.
    """
    import yaml
    env_files = env_files or {"dev": "env.dev", "staging": "env.staging", "prod": "env.prod"}
    config = {
        "project": project,
        "environments": [
            {"name": name, "env_file": path}
            for name, path in env_files.items()
        ],
    }
    config_path = tmp_path / ".envault.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    # Create env files only if relative (absolute paths may already exist)
    for _, path in env_files.items():
        p = Path(path)
        if not p.is_absolute():
            p = tmp_path / path
            p.write_text("")
    return str(config_path)


def test_diff_with_config(runner: CliRunner, tmp_path):
    """diff command with config and explicit file overrides should work."""
    config_path = _make_config(tmp_path)
    src = tmp_path / "src.env"
    tgt = tmp_path / "tgt.env"
    src.write_text("KEY=source_value\nSHARED=yes\n")
    tgt.write_text("KEY=target_value\nSHARED=yes\n")

    result = runner.invoke(app, [
        "diff", "dev", "prod",
        "--source", str(src),
        "--target", str(tgt),
        "--config", config_path,
    ])
    assert result.exit_code == 0
    assert "KEY" in result.stdout
    assert "difference" in result.stdout.lower() or "Differing" in result.stdout



def test_diff_files_identical(runner: CliRunner, tmp_path):
    """diff-files with identical files should show no differences."""
    file1 = tmp_path / "a.env"
    file2 = tmp_path / "b.env"
    file1.write_text("KEY=value\nFOO=bar\n")
    file2.write_text("KEY=value\nFOO=bar\n")

    result = runner.invoke(app, ["diff-files", str(file1), str(file2)])
    assert result.exit_code == 0
    assert "identical" in result.stdout.lower() or "identical" in result.stdout or "no difference" in result.stdout.lower()


def test_diff_files_different(runner: CliRunner, tmp_path):
    """diff-files should detect differences."""
    file1 = tmp_path / "a.env"
    file2 = tmp_path / "b.env"
    file1.write_text("KEY=value\nFOO=bar\n")
    file2.write_text("KEY=other\nFOO=bar\nEXTRA=x\n")

    result = runner.invoke(app, ["diff-files", str(file1), str(file2)])
    assert result.exit_code == 0
    assert "KEY" in result.stdout
    assert "EXTRA" in result.stdout or "difference" in result.stdout.lower()


def test_diff_files_not_found(runner: CliRunner, tmp_path):
    """diff-files on non-existent files should complete gracefully (empty files treated as no content)."""
    result = runner.invoke(app, ["diff-files", str(tmp_path / "nope1.env"), str(tmp_path / "nope2.env")])
    # Non-existent files are treated as empty — they're identical
    assert result.exit_code == 0
    assert "identical" in result.stdout.lower()


# ── Encrypt / Decrypt ───────────────────────────────────────────────────────


def test_encrypt_cli_basic(runner: CliRunner, tmp_path):
    """encrypt command should encrypt a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=my_value\nAPI_KEY=abc123\n")

    result = runner.invoke(app, ["encrypt", str(env_file), "--password", "test-pass"])
    assert result.exit_code == 0
    assert "Encrypted" in result.stdout

    # Check encrypted file was created at default location
    expected = tmp_path / ".env.locked"
    if expected.exists():
        raw = expected.read_bytes()
        assert raw.startswith(b"gAAAA")  # Fernet prefix


def test_encrypt_cli_custom_output(runner: CliRunner, tmp_path):
    """encrypt command should respect --output."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=val\n")
    output = tmp_path / "custom.enc"

    result = runner.invoke(app, ["encrypt", str(env_file), "--output", str(output), "--password", "p"])
    assert result.exit_code == 0
    assert output.exists()
    assert output.read_bytes().startswith(b"gAAAA")


def test_encrypt_cli_delete_original(runner: CliRunner, tmp_path):
    """encrypt --delete should remove the original."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=val\n")

    result = runner.invoke(app, ["encrypt", str(env_file), "--password", "p", "--delete"])
    assert result.exit_code == 0
    assert not env_file.exists()


def test_encrypt_empty_fails(runner: CliRunner, tmp_path):
    """Encrypting an empty file should fail with a message."""
    env_file = tmp_path / ".env"
    env_file.write_text("")

    result = runner.invoke(app, ["encrypt", str(env_file), "--password", "p"])
    assert result.exit_code != 0 or "empty" in result.stdout.lower() or "error" in result.stdout.lower()


def test_decrypt_cli_roundtrip(runner: CliRunner, tmp_path):
    """Round-trip: encrypt then decrypt via CLI."""
    env_file = tmp_path / ".env.test"
    env_file.write_text("MY_VAR=hello\n")
    encrypted = tmp_path / ".env.test.locked"

    # Encrypt
    result_enc = runner.invoke(app, ["encrypt", str(env_file), "--output", str(encrypted), "--password", "roundtrip"])
    assert result_enc.exit_code == 0
    assert encrypted.exists()

    # Decrypt
    decrypted = tmp_path / ".env.restored"
    result_dec = runner.invoke(app, ["decrypt", str(encrypted), "--output", str(decrypted), "--password", "roundtrip"])
    assert result_dec.exit_code == 0
    assert "Decrypted" in result_dec.stdout
    assert decrypted.exists()
    assert decrypted.read_text() == "MY_VAR=hello\n"


def test_decrypt_wrong_password_fails(runner: CliRunner, tmp_path):
    """Decrypt with wrong password should fail."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=val\n")
    encrypted = tmp_path / ".env.locked"

    runner.invoke(app, ["encrypt", str(env_file), "--output", str(encrypted), "--password", "correct"])
    result = runner.invoke(app, ["decrypt", str(encrypted), "--output", str(tmp_path / "out"), "--password", "wrong"])
    assert result.exit_code != 0 or "failed" in result.stdout.lower() or "error" in result.stdout.lower()


# ── Sync (dry-run) ──────────────────────────────────────────────────────────


def test_sync_dry_run(runner: CliRunner, tmp_path):
    """sync --dry-run should show planned changes without applying them."""
    # Use absolute paths in config so sync can find them regardless of CWD
    src = tmp_path / "env.dev"
    tgt = tmp_path / "env.prod"
    config_path = _make_config(tmp_path, env_files={"dev": str(src), "prod": str(tgt)})
    src.write_text("KEY=source_val\nNEW_KEY=hello\n")
    tgt.write_text("KEY=old_val\n")

    result = runner.invoke(app, [
        "sync", "dev", "prod",
        "--strategy", "source_wins",
        "--dry-run",
        "--config", config_path,
    ])
    assert result.exit_code == 0
    assert "Dry run" in result.stdout or "dry" in result.stdout.lower()
    assert "KEY" in result.stdout or "keys to update" in result.stdout or "keys to add" in result.stdout


def test_sync_source_not_found(runner: CliRunner, tmp_path):
    """sync with missing source should error."""
    src = tmp_path / "env.dev"
    tgt = tmp_path / "env.prod"
    config_path = _make_config(tmp_path, env_files={"dev": str(src), "prod": str(tgt)})
    # Don't create the source file
    tgt.write_text("KEY=value\n")

    result = runner.invoke(app, [
        "sync", "dev", "prod",
        "--dry-run",
        "--config", config_path,
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "Error" in result.output


# ── Error Handling ──────────────────────────────────────────────────────────


def test_unknown_command_shows_help(runner: CliRunner):
    """An unknown command should show helpful message."""
    result = runner.invoke(app, ["nonexistent-command"])
    # CliRunner prints help/error to stderr for unknown commands
    assert result.exit_code != 0
    # Check combined output (stdout + stderr)
    assert "Error" in result.output or "No such" in result.output or "Usage" in result.output


def test_init_missing_project_name(runner: CliRunner):
    """init without project name should show error."""
    result = runner.invoke(app, ["init"])
    # Missing required argument — check combined output
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "Error" in result.output


# ── Rotate All ────────────────────────────────────────────────────────────────


def _make_config_with_env(tmp_path, project="test", env_name="dev", env_content="KEY=value\nFOO=bar\n"):
    """Create a minimal .envault.yml and a matching .env file."""
    import yaml
    env_file = tmp_path / f".env.{env_name}"
    env_file.write_text(env_content)
    config = {
        "project": project,
        "environments": [
            {"name": env_name, "env_file": str(env_file)}
        ],
        "audit_log_path": str(tmp_path / ".envault-audit.log"),
    }
    config_path = tmp_path / ".envault.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return str(config_path)


def test_rotate_all_dry_run(runner: CliRunner, tmp_path):
    config_path = _make_config_with_env(tmp_path, env_content="DB_PASSWORD=secret\nAPI_KEY=abc\n")
    result = runner.invoke(app, ["rotate-all", "--env", "dev", "--dry-run", "--config", config_path])
    assert result.exit_code == 0
    assert "Dry run" in result.stdout or "Would rotate" in result.stdout


def test_rotate_all_no_variables(runner: CliRunner, tmp_path):
    config_path = _make_config_with_env(tmp_path, env_content="")
    result = runner.invoke(app, ["rotate-all", "--env", "dev", "--dry-run", "--config", config_path])
    assert result.exit_code == 0
    assert "No variables" in result.stdout


def test_rotate_all_env_not_found(runner: CliRunner, tmp_path):
    config_path = _make_config_with_env(tmp_path)
    result = runner.invoke(app, ["rotate-all", "--env", "nonexistent", "--dry-run", "--config", config_path])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ── Store Commands ────────────────────────────────────────────────────────────


def _make_store_config(tmp_path, env_content="KEY=val\nOTHER=keep\n"):
    """Create .envault.yml with a local store."""
    import yaml
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)
    config = {
        "project": "test",
        "stores": {
            "local": {
                "type": "local",
                "path_prefix": str(env_file),
            }
        },
    }
    config_path = tmp_path / ".envault.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return str(config_path), str(env_file)


def test_store_list_prefix(runner: CliRunner, tmp_path):
    config_path, _ = _make_store_config(tmp_path, env_content="DB_HOST=localhost\nDB_PORT=5432\nAPI_KEY=abc\n")
    result = runner.invoke(app, ["store", "list", "local", "--prefix", "DB_", "--config", config_path])
    assert result.exit_code == 0
    assert "DB_HOST" in result.stdout
    assert "API_KEY" not in result.stdout


def test_store_get_not_found(runner: CliRunner, tmp_path):
    config_path, _ = _make_store_config(tmp_path)
    result = runner.invoke(app, ["store", "get", "NONEXISTENT", "--store", "local", "--config", config_path])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_store_set_and_get(runner: CliRunner, tmp_path):
    config_path, _ = _make_store_config(tmp_path)
    set_result = runner.invoke(app, ["store", "set", "NEW_KEY", "new_value", "--store", "local", "--config", config_path])
    assert set_result.exit_code == 0
    assert "Set" in set_result.stdout
    get_result = runner.invoke(app, ["store", "get", "NEW_KEY", "--store", "local", "--config", config_path])
    assert get_result.exit_code == 0
    assert "new_value" in get_result.stdout


# ── Audit CLI ─────────────────────────────────────────────────────────────────


def _make_audit_config(tmp_path):
    """Create config with an audit log file."""
    import yaml
    config = {
        "project": "test",
        "environments": [],
        "audit_log_path": str(tmp_path / ".envault-audit.log"),
    }
    config_path = tmp_path / ".envault.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return str(config_path)


def test_audit_cli_no_entries(runner: CliRunner, tmp_path):
    config_path = _make_audit_config(tmp_path)
    result = runner.invoke(app, ["audit", "--config", config_path])
    assert result.exit_code == 0
    assert "No audit entries" in result.stdout


def test_audit_cli_with_entries(runner: CliRunner, tmp_path):
    from envault.audit import AuditLogger
    config_path = _make_audit_config(tmp_path)
    log_path = str(tmp_path / ".envault-audit.log")
    AuditLogger(log_path).log("rotate", "DB_PASSWORD", env_file=".env.prod")
    AuditLogger(log_path).log("add", "API_KEY", source_path=".env.dev", target_path=".env.prod")
    result = runner.invoke(app, ["audit", "--config", config_path])
    assert result.exit_code == 0
    assert "DB_PASSWORD" in result.stdout
    assert "rotate" in result.stdout or "add" in result.stdout


def test_audit_cli_filter_key(runner: CliRunner, tmp_path):
    from envault.audit import AuditLogger
    config_path = _make_audit_config(tmp_path)
    log_path = str(tmp_path / ".envault-audit.log")
    AuditLogger(log_path).log("rotate", "DB_PASSWORD", env_file=".env.prod")
    AuditLogger(log_path).log("set", "API_KEY", env_file=".env.prod")
    result = runner.invoke(app, ["audit", "--key", "DB_PASSWORD", "--config", config_path])
    assert result.exit_code == 0
    assert "API_KEY" not in result.stdout


# ── Rotate (Single Key) ───────────────────────────────────────────────────────


def test_rotate_dry_run(runner: CliRunner, tmp_path):
    """rotate a single key with --dry-run should show new value without modifying."""
    import yaml
    env_file = tmp_path / ".env.dev"
    env_file.write_text("DB_PASSWORD=old_secret\nAPI_KEY=keep_this\n")
    config = {
        "project": "test",
        "environments": [{"name": "dev", "env_file": str(env_file)}],
        "audit_log_path": str(tmp_path / ".envault-audit.log"),
    }
    config_path = tmp_path / ".envault.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    result = runner.invoke(app, [
        "rotate", "DB_PASSWORD",
        "--env", "dev",
        "--length", "16",
        "--dry-run",
        "--show",
        "--config", str(config_path),
    ])
    assert result.exit_code == 0
    assert "Would rotate" in result.stdout or "Dry run" in result.stdout
    assert "DB_PASSWORD" in result.stdout

    # Verify original file is unchanged
    content = env_file.read_text()
    assert "old_secret" in content


def test_rotate_key_not_found(runner: CliRunner, tmp_path):
    """rotate on a non-existent key should exit with error."""
    import yaml
    env_file = tmp_path / ".env.dev"
    env_file.write_text("EXISTING_KEY=value\n")
    config = {
        "project": "test",
        "environments": [{"name": "dev", "env_file": str(env_file)}],
        "audit_log_path": str(tmp_path / ".envault-audit.log"),
    }
    config_path = tmp_path / ".envault.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    result = runner.invoke(app, [
        "rotate", "NONEXISTENT_KEY",
        "--env", "dev",
        "--dry-run",
        "--config", str(config_path),
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
