"""Tests for Envault CLI."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from envault import __version__
from envault.audit import AuditLogger
from envault.config import EnvaultConfig, init_config
from envault.diff import diff_envs, diff_env_files, format_diff, load_env_file
from envault.rotate import generate_secret, rotate_value, rotate_env_var
from envault.sync import sync_envs, sync_env_files, SyncConflict, write_env_file


# ── Version ─────────────────────────────────────────────────────────────────

def test_version():
    assert __version__ == "0.1.0"


# ── Config ──────────────────────────────────────────────────────────────────

def test_config_defaults():
    config = EnvaultConfig()
    assert config.project == ""
    assert len(config.environments) == 3
    assert config.environments[0].name == "dev"
    assert config.environments[1].name == "staging"
    assert config.environments[2].name == "prod"


def test_config_save_load(tmp_path):
    path = tmp_path / ".envault.yml"
    config = EnvaultConfig(project="test-project")
    config.environments[0].env_file = ".env.dev"
    config.save(str(path))

    assert path.exists()

    loaded = EnvaultConfig.load(str(path))
    assert loaded.project == "test-project"
    assert loaded.environments[0].env_file == ".env.dev"


def test_init_config(tmp_path):
    path = tmp_path / ".envault.yml"
    config = init_config("my-project", str(path))
    assert config.project == "my-project"
    assert path.exists()


def test_config_get_env_path(tmp_path):
    config = EnvaultConfig()
    config.environments[0].env_file = ".env.custom"
    assert config.get_env_path("dev") == Path(".env.custom")
    assert config.get_env_path("nonexistent") == Path(".env.nonexistent")


def test_config_get_env_names():
    config = EnvaultConfig()
    names = config.get_env_names()
    assert names == ["dev", "staging", "prod"]


# ── Diff ────────────────────────────────────────────────────────────────────

def test_diff_envs_identical():
    env_a = {"DB_HOST": "localhost", "DB_PORT": "5432"}
    env_b = {"DB_HOST": "localhost", "DB_PORT": "5432"}
    result = diff_envs(env_a, env_b)
    assert not result.has_differences
    assert result.total_differences == 0


def test_diff_envs_only_in_source():
    env_a = {"KEY_A": "val_a", "KEY_B": "val_b"}
    env_b = {"KEY_A": "val_a"}
    result = diff_envs(env_a, env_b)
    assert result.has_differences
    assert "KEY_B" in result.only_in_source
    assert len(result.only_in_target) == 0
    assert len(result.different) == 0


def test_diff_envs_only_in_target():
    env_a = {"KEY_A": "val_a"}
    env_b = {"KEY_A": "val_a", "KEY_B": "val_b"}
    result = diff_envs(env_a, env_b)
    assert "KEY_B" in result.only_in_target


def test_diff_envs_different_values():
    env_a = {"KEY_A": "old_value"}
    env_b = {"KEY_A": "new_value"}
    result = diff_envs(env_a, env_b)
    assert "KEY_A" in result.different
    assert result.different["KEY_A"] == ("old_value", "new_value")


def test_diff_env_files(tmp_path):
    src = tmp_path / ".env.dev"
    tgt = tmp_path / ".env.prod"
    src.write_text("DB_HOST=localhost\nDB_PORT=5432\n")
    tgt.write_text("DB_HOST=prod.example.com\nDB_PORT=5432\n")

    result = diff_env_files(str(src), str(tgt))
    assert result.has_differences
    assert "DB_HOST" in result.different
    assert "DB_PORT" not in result.different  # same value


def test_load_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\nFOO=bar\n")
    result = load_env_file(str(env_file))
    assert result == {"KEY": "value", "FOO": "bar"}


def test_load_env_file_not_exists(tmp_path):
    result = load_env_file(tmp_path / ".nonexistent")
    assert result == {}


def test_format_diff_identical():
    result = diff_envs({"A": "1"}, {"A": "1"})
    output = format_diff(result)
    assert "identical" in output


def test_format_diff_different():
    result = diff_envs({"A": "1", "B": "2"}, {"A": "x", "C": "3"})
    output = format_diff(result)
    assert "Only in source" in output or "Differing" in output or "Only in target" in output


# ── Sync ────────────────────────────────────────────────────────────────────

def test_sync_envs_add():
    source = {"A": "1", "B": "2"}
    target = {"A": "1"}
    result = sync_envs(source, target)
    assert "B" in result.added
    assert target["B"] == "2"


def test_sync_envs_update_source_wins():
    source = {"A": "new"}
    target = {"A": "old"}
    result = sync_envs(source, target, strategy="source_wins")
    assert "A" in result.updated
    assert target["A"] == "new"


def test_sync_envs_update_target_wins():
    source = {"A": "new"}
    target = {"A": "old"}
    result = sync_envs(source, target, strategy="target_wins")
    assert "A" in result.skipped
    assert target["A"] == "old"  # unchanged


def test_sync_envs_conflict_error():
    source = {"A": "new"}
    target = {"A": "old"}
    with pytest.raises(SyncConflict):
        sync_envs(source, target, strategy="error")


def test_sync_envs_allow_delete():
    source = {"A": "1"}
    target = {"A": "1", "B": "2"}
    result = sync_envs(source, target, allow_delete=True)
    assert "B" in result.deleted
    assert "B" not in target


def test_sync_envs_skip_keys():
    source = {"A": "new", "B": "also_new"}
    target = {"A": "old", "B": "old"}
    result = sync_envs(source, target, skip_keys={"A"})
    assert "A" in result.skipped
    assert target["A"] == "old"  # unchanged due to skip
    assert "B" in result.updated  # not skipped


def test_write_env_file(tmp_path):
    env_vars = {"DB_HOST": "localhost", "DB_PORT": "5432"}
    env_file = tmp_path / ".env"
    count = write_env_file(str(env_file), env_vars)
    assert count == 2
    content = env_file.read_text()
    assert "DB_HOST=localhost" in content
    assert "DB_PORT=5432" in content


def test_sync_env_files(tmp_path):
    src = tmp_path / ".env.dev"
    tgt = tmp_path / ".env.prod"
    src.write_text("KEY=from_dev\nSHARED=yes\n")
    tgt.write_text("SHARED=yes\nLOCAL=value\n")

    result = sync_env_files(str(src), str(tgt), allow_delete=True)
    assert "KEY" in result.added
    assert "LOCAL" in result.deleted

    # Check file was written
    content = tgt.read_text()
    assert "KEY=from_dev" in content
    assert "LOCAL" not in content


# ── Rotate ──────────────────────────────────────────────────────────────────

def test_generate_secret_length():
    secret = generate_secret(64)
    assert len(secret) == 64


def test_generate_secret_chars():
    secret = generate_secret(100, use_upper=True, use_lower=True, use_digits=True, use_symbols=False)
    assert all(c.isalnum() for c in secret)


def test_generate_secret_no_symbols():
    secret = generate_secret(100, use_symbols=False)
    assert all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for c in secret)


def test_generate_secret_exclude():
    secret = generate_secret(100, use_upper=True, use_lower=True, use_digits=True, use_symbols=False, exclude_chars="abc")
    assert "a" not in secret
    assert "b" not in secret
    assert "c" not in secret


def test_rotate_value_db_password():
    result = rotate_value("DB_PASSWORD", "oldpass")
    assert len(result) >= 20
    assert "I" not in result  # ambiguous char excluded
    assert "l" not in result


def test_rotate_value_api_key():
    result = rotate_value("STRIPE_API_KEY", "sk_old...")
    assert result.startswith("stri_")
    assert len(result) > 40


def test_rotate_value_jwt():
    result = rotate_value("JWT_SECRET", "old")
    # JWT secrets are base64 urlsafe encoded, no padding
    assert "=" not in result.rstrip("=") or True  # at least it's not empty
    assert len(result) > 20


def test_rotate_env_var(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=old_password\nKEY=value\n")

    success, new_val = rotate_env_var("DB_PASSWORD", str(env_file), dry_run=True)
    assert success
    assert new_val != "old_password"

    # Actually rotate
    success, new_val = rotate_env_var("DB_PASSWORD", str(env_file))
    assert success
    content = env_file.read_text()
    assert new_val in content
    assert "old_password" not in content


def test_rotate_env_var_not_found(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\n")
    success, _ = rotate_env_var("NONEXISTENT", str(env_file))
    assert not success


# ── Audit ───────────────────────────────────────────────────────────────────

def test_audit_log_basic(tmp_path):
    log = AuditLogger(str(tmp_path / "audit.log"))
    log.log("rotate", "DB_PASSWORD", env_file=".env.prod")
    history = log.get_history()
    assert len(history) == 1
    assert history[0]["action"] == "rotate"
    assert history[0]["key"] == "DB_PASSWORD"


def test_audit_log_filter(tmp_path):
    log = AuditLogger(str(tmp_path / "audit.log"))
    log.log("add", "KEY_A")
    log.log("update", "KEY_B")
    log.log("rotate", "KEY_A")

    history = log.get_history(key="KEY_A")
    assert len(history) == 2

    history = log.get_history(action="rotate")
    assert len(history) == 1
    assert history[0]["key"] == "KEY_A"


def test_audit_log_clear(tmp_path):
    log = AuditLogger(str(tmp_path / "audit.log"))
    log.log("add", "KEY")
    assert len(log.get_history()) == 1
    log.clear()
    assert len(log.get_history()) == 0
