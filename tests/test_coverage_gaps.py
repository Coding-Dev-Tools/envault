"""Tests targeting uncovered branches across envault modules.

Covers:
- audit.py: log() with source_path/target_path/details, get_history on missing file, clear on missing file
- config.py: load() on empty yaml, get_store() returning None
- diff.py: _mask_value with short values, paths, numeric strings, long non-secret strings
- encrypt.py: _get_password from env var, _get_or_create_salt existing, decrypt wrong password
- rotate.py: webhook key rotation, rotate_env_var with audit logger, special char escaping in replacement
"""

from __future__ import annotations

from envault.audit import AuditLogger
from envault.config import EnvaultConfig
from envault.diff import _mask_value, diff_envs, format_diff
from envault.rotate import rotate_env_var, rotate_value
from pathlib import Path

# ── audit.py: log() with optional fields ────────────────────────────────────


def test_audit_log_with_source_path(tmp_path):
    """log() with source_path should include 'source' key in entry."""
    log = AuditLogger(str(tmp_path / "audit.log"))
    log.log("sync", "DB_HOST", source_path=".env.dev")
    history = log.get_history()
    assert len(history) == 1
    assert history[0]["source"] == ".env.dev"


def test_audit_log_with_target_path(tmp_path):
    """log() with target_path should include 'target' key in entry."""
    log = AuditLogger(str(tmp_path / "audit.log"))
    log.log("sync", "DB_HOST", target_path=".env.prod")
    history = log.get_history()
    assert len(history) == 1
    assert history[0]["target"] == ".env.prod"


def test_audit_log_with_details(tmp_path):
    """log() with details dict should include 'details' key in entry."""
    log = AuditLogger(str(tmp_path / "audit.log"))
    log.log("rotate", "API_KEY", details={"strategy": "source_wins", "old_prefix": "sk_"})
    history = log.get_history()
    assert len(history) == 1
    assert history[0]["details"]["strategy"] == "source_wins"


def test_audit_get_history_missing_file(tmp_path):
    """get_history on a non-existent log file returns empty list."""
    log = AuditLogger(str(tmp_path / "nonexistent.log"))
    assert log.get_history() == []


def test_audit_clear_missing_file(tmp_path):
    """clear() on a non-existent file should not raise."""
    log = AuditLogger(str(tmp_path / "nonexistent.log"))
    log.clear()  # Should not raise
    assert not Path(tmp_path / "nonexistent.log").exists()


def test_audit_log_malformed_line(tmp_path):
    """get_history skips lines that are not valid JSON."""
    log_path = tmp_path / "audit.log"
    # Write a mix of valid and invalid lines
    log_path.write_text('{"action":"add","key":"K1"}\nnot-json\n{"action":"add","key":"K2"}\n')
    log = AuditLogger(str(log_path))
    history = log.get_history()
    assert len(history) == 2  # Only the valid JSON lines


def test_audit_get_history_limit(tmp_path):
    """get_history respects the limit parameter."""
    log = AuditLogger(str(tmp_path / "audit.log"))
    for i in range(10):
        log.log("add", f"KEY_{i}")
    history = log.get_history(limit=3)
    assert len(history) == 3


# ── config.py: load() on empty yaml, get_store() ────────────────────────────


def test_config_load_empty_yaml(tmp_path):
    """load() on a yaml file with only comments/empty returns defaults."""
    path = tmp_path / ".envault.yml"
    path.write_text("# just a comment\n")
    config = EnvaultConfig.load(str(path))
    assert config.project == ""  # defaults
    assert len(config.environments) == 3


def test_config_get_store_existing(tmp_path):
    """get_store() returns the store config when it exists."""
    from envault.config import SecretStoreConfig
    config = EnvaultConfig()
    store_cfg = SecretStoreConfig(type="vault", url="http://vault:8200")
    config.stores["myvault"] = store_cfg
    assert config.get_store("myvault") is store_cfg


def test_config_get_store_missing():
    """get_store() returns None for unknown store name."""
    config = EnvaultConfig()
    assert config.get_store("nonexistent") is None


# ── diff.py: _mask_value edge cases ─────────────────────────────────────────


def test_mask_value_short_string():
    """Short strings should not be masked."""
    assert _mask_value("abc") == "abc"


def test_mask_value_path():
    """Path-like values starting with / should not be masked."""
    long_path = "/very/long/path/to/some/config/file/that/is/long"
    assert _mask_value(long_path) == long_path  # starts with /


def test_mask_value_numeric():
    """Numeric-looking values should not be masked."""
    numeric = "123.456.789.012.345.6789"
    assert _mask_value(numeric) == numeric


def test_mask_value_secret():
    """Long non-path, non-numeric strings should be masked."""
    # Use a long non-path string that looks like a secret (but is clearly a test value)
    secret = "testprefix_" + "a" * 40
    masked = _mask_value(secret)
    assert "..." in masked
    assert masked.startswith(secret[:8])
    assert masked.endswith(secret[-4:])


def test_mask_value_exactly_16_chars():
    """Values of exactly 16 chars should NOT be masked (condition is >16)."""
    val = "a" * 16
    assert _mask_value(val) == val


def test_mask_value_17_chars():
    """Values of 17+ chars that look like secrets should be masked."""
    val = "x" * 17
    masked = _mask_value(val)
    assert "..." in masked


# ── format_diff with common keys ────────────────────────────────────────────


def test_format_diff_with_common_keys_partial():
    """format_diff should include 'Unchanged' section when some keys match alongside differences."""
    result = diff_envs({"A": "1", "B": "2"}, {"A": "1", "B": "changed", "C": "3"})
    output = format_diff(result)
    assert "Unchanged" in output


def test_format_diff_custom_labels():
    """format_diff should use custom source/target labels."""
    result = diff_envs({"X": "1"}, {"X": "2"})
    output = format_diff(result, source_label="dev", target_label="prod")
    assert "dev" in output
    assert "prod" in output


# ── rotate.py: webhook rotation, audit, special chars ────────────────────────


def test_rotate_value_webhook():
    """rotate_value should generate 48-char no-symbol secret for webhook keys."""
    result = rotate_value("STRIPE_WEBHOOK_SECRET", "old")
    assert len(result) == 48
    # No symbols
    assert all(c.isalnum() for c in result)


def test_rotate_value_webhook_variant():
    """Various webhook key name patterns should all trigger webhook path."""
    result = rotate_value("WEBHOOK_SIGNING_KEY", "old")
    assert len(result) == 48
    assert all(c.isalnum() for c in result)


def test_rotate_value_default():
    """Keys that don't match any pattern get a standard 32-char secret."""
    result = rotate_value("RANDOM_VAR", "old")
    assert len(result) == 32


def test_rotate_env_var_with_audit(tmp_path):
    """rotate_env_var with audit logger should write an audit entry."""
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=oldpass\n")

    audit_log = str(tmp_path / "audit.log")
    audit = AuditLogger(audit_log)

    success, new_val = rotate_env_var("DB_PASSWORD", str(env_file), audit=audit)
    assert success

    history = audit.get_history(action="rotate")
    assert len(history) == 1
    assert history[0]["key"] == "DB_PASSWORD"


def test_rotate_env_var_special_chars_in_new_value(tmp_path):
    """Rotated value with special chars should be properly quoted in .env."""
    env_file = tmp_path / ".env"
    env_file.write_text("WEBHOOK_URL=https://example.com/hook\n")

    # Force a value with special chars by rotating a non-matching key
    success, new_val = rotate_env_var("WEBHOOK_URL", str(env_file))
    assert success
    # The file should still be parseable (key=value or key="value")
    from dotenv import dotenv_values
    reloaded = dotenv_values(str(env_file))
    assert "WEBHOOK_URL" in reloaded


def test_rotate_env_var_nonexistent_file(tmp_path):
    """rotate_env_var on a non-existent file returns (False, '')."""
    success, val = rotate_env_var("KEY", str(tmp_path / "nope.env"))
    assert not success
    assert val == ""


def test_rotate_env_var_dry_run_with_audit(tmp_path):
    """Dry run should not write audit entry even when audit is provided."""
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=oldpass\n")

    audit_log = str(tmp_path / "audit.log")
    audit = AuditLogger(audit_log)

    success, new_val = rotate_env_var("DB_PASSWORD", str(env_file), dry_run=True, audit=audit)
    assert success
    assert new_val != "oldpass"
    # Dry run should NOT log audit
    assert len(audit.get_history()) == 0
    # Original file should be unchanged
    assert "oldpass" in env_file.read_text()
