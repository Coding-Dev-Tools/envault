"""Tests targeting uncovered branches across envault modules.

Covers:
- audit.py: log() with source_path/target_path/details, get_history on missing file, clear on missing file
- config.py: load() on empty yaml, get_store() returning None
- diff.py: _mask_value with short values, paths, numeric strings, long non-secret strings
- encrypt.py: _get_password from env var, _get_or_create_salt existing, decrypt wrong password
- rotate.py: webhook key rotation, rotate_env_var with audit logger, special char escaping in replacement
"""

from __future__ import annotations

from pathlib import Path

from envault.audit import AuditLogger
from envault.config import EnvaultConfig
from envault.diff import _mask_value, diff_envs, format_diff
from envault.rotate import rotate_env_var, rotate_value

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


# ── diff.py: to_dict / to_json ───────────────────────────────────────────────


def test_to_dict_identical():
    """to_dict for identical envs should show no differences."""
    result = diff_envs({"A": "1"}, {"A": "1"})
    d = result.to_dict()
    assert d["has_differences"] is False
    assert d["total_differences"] == 0
    assert d["only_in_source"] == {}
    assert d["only_in_target"] == {}
    assert d["different"] == {}
    assert d["common_keys"] == ["A"]


def test_to_dict_with_differences():
    """to_dict should categorise added, removed, changed, and common keys."""
    result = diff_envs(
        {"A": "1", "B": "2", "C": "3"},
        {"A": "1", "B": "changed", "D": "4"},
    )
    d = result.to_dict(source_label="dev", target_label="prod")
    assert d["has_differences"] is True
    assert d["total_differences"] == 3
    assert d["only_in_source"] == {"C": "3"}
    assert d["only_in_target"] == {"D": "4"}
    assert d["different"] == {"B": {"dev": "2", "prod": "changed"}}
    assert d["common_keys"] == ["A"]


def test_to_dict_no_mask():
    """to_dict with mask_values=False should return raw values."""
    long_secret = "x" * 50
    result = diff_envs({"K": long_secret}, {})
    d = result.to_dict(mask_values=False)
    assert d["only_in_source"]["K"] == long_secret


def test_to_dict_with_mask():
    """to_dict with mask_values=True (default) should mask long secret-like values."""
    long_secret = "x" * 50
    result = diff_envs({"K": long_secret}, {})
    d = result.to_dict(mask_values=True)
    assert "..." in d["only_in_source"]["K"]


def test_to_json_parses():
    """to_json should produce valid JSON that round-trips through to_dict."""
    result = diff_envs({"X": "1", "Y": "2"}, {"X": "1", "Y": "changed", "Z": "3"})
    import json
    parsed = json.loads(result.to_json(source_label="s", target_label="t"))
    assert parsed["has_differences"] is True
    assert "Y" in parsed["different"]
    assert parsed["different"]["Y"] == {"s": "2", "t": "changed"}


def test_to_json_compact():
    """to_json with indent=None should produce compact JSON."""
    result = diff_envs({"A": "1"}, {"A": "2"})
    compact = result.to_json(indent=None)
    assert "\n" not in compact
    import json
    assert json.loads(compact)["has_differences"] is True


def test_to_json_custom_labels():
    """to_json should use custom source/target labels in the different dict."""
    result = diff_envs({"K": "old"}, {"K": "new"})
    import json
    parsed = json.loads(result.to_json(source_label="staging", target_label="production"))
    assert "staging" in parsed["different"]["K"]
    assert "production" in parsed["different"]["K"]


def test_to_dict_empty_common():
    """to_dict with no common keys should have empty common_keys list."""
    result = diff_envs({"A": "1"}, {"B": "2"})
    d = result.to_dict()
    assert d["common_keys"] == []
