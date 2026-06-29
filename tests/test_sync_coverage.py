"""Tests targeting uncovered branches in sync.py (80% → higher).

Covers:
- SyncResult.__str__ (all branches: added, updated, deleted, conflicts, skipped, "No changes")
- SyncConflict.__init__ and message formatting
- sync_envs: skip_keys in add and delete branches
- write_env_file: values with special characters (#, quotes, backslash, newlines)
- sync_env_files: audit logging for add/update/delete
"""

from __future__ import annotations

from envault.audit import AuditLogger
from envault.sync import (
    SyncConflict,
    SyncResult,
    sync_env_files,
    sync_envs,
    write_env_file,
)

# ── SyncResult.__str__ ──────────────────────────────────────────────────────


def test_sync_result_str_no_changes():
    """Empty SyncResult should display 'No changes'."""
    result = SyncResult()
    assert str(result) == "No changes"


def test_sync_result_str_added_only():
    result = SyncResult()
    result.added = ["KEY_A"]
    assert str(result) == "+ 1 added"


def test_sync_result_str_updated_only():
    result = SyncResult()
    result.updated = ["KEY_B"]
    assert str(result) == "~ 1 updated"


def test_sync_result_str_deleted_only():
    result = SyncResult()
    result.deleted = ["KEY_C"]
    assert str(result) == "- 1 deleted"


def test_sync_result_str_conflicts_only():
    result = SyncResult()
    result.conflicts = [SyncConflict("X", "src", "tgt")]
    assert str(result) == "! 1 conflicts"


def test_sync_result_str_skipped_only():
    result = SyncResult()
    result.skipped = ["KEY_D"]
    assert str(result) == "- 1 skipped"


def test_sync_result_str_mixed():
    """Multiple categories should be comma-separated."""
    result = SyncResult()
    result.added = ["A", "B"]
    result.updated = ["C"]
    result.deleted = ["D"]
    result.conflicts = [SyncConflict("E", "s", "t")]
    result.skipped = ["F"]
    text = str(result)
    assert "+ 2 added" in text
    assert "~ 1 updated" in text
    assert "- 1 deleted" in text
    assert "! 1 conflicts" in text
    assert "- 1 skipped" in text
    # All parts joined by ", "
    assert text.count(", ") == 4  # 5 parts → 4 commas


# ── SyncConflict ────────────────────────────────────────────────────────────


def test_sync_conflict_init():
    """SyncConflict stores key, source_value, target_value."""
    conflict = SyncConflict("API_KEY", "source_val", "target_val")
    assert conflict.key == "API_KEY"
    assert conflict.source_value == "source_val"
    assert conflict.target_value == "target_val"


def test_sync_conflict_message_truncation():
    """SyncConflict message truncates values to 20 chars with '...'."""
    long_source = "a" * 30
    long_target = "b" * 30
    conflict = SyncConflict("KEY", long_source, long_target)
    msg = str(conflict)
    assert "aaaa" in msg  # first 20 chars of source
    assert "..." in msg
    assert "bbbb" in msg


def test_sync_conflict_short_values():
    """Short values appear in full without truncation."""
    conflict = SyncConflict("KEY", "short_src", "short_tgt")
    msg = str(conflict)
    assert "short_src" in msg
    assert "short_tgt" in msg


# ── sync_envs: skip_keys in add branch ─────────────────────────────────────


def test_sync_envs_skip_keys_on_add():
    """skip_keys should prevent adding a key that exists only in source."""
    source = {"NEW_KEY": "val", "OTHER": "x"}
    target = {"OTHER": "x"}
    result = sync_envs(source, target, skip_keys={"NEW_KEY"})
    assert "NEW_KEY" in result.skipped
    assert "NEW_KEY" not in result.added
    assert "NEW_KEY" not in target  # should not have been added


# ── sync_envs: skip_keys in delete branch ───────────────────────────────────


def test_sync_envs_skip_keys_on_delete():
    """skip_keys should prevent deleting a key in target that's absent from source."""
    source = {"A": "1"}
    target = {"A": "1", "PROTECTED": "keep"}
    result = sync_envs(source, target, allow_delete=True, skip_keys={"PROTECTED"})
    assert "PROTECTED" in result.skipped
    assert "PROTECTED" not in result.deleted
    assert "PROTECTED" in target  # should NOT have been deleted


def test_sync_envs_skip_keys_on_add_and_delete():
    """skip_keys works simultaneously for add and delete branches."""
    source = {"A": "1"}
    target = {"A": "1", "SKIP_DEL": "x"}
    result = sync_envs(
        source, target, allow_delete=True, skip_keys={"SKIP_ADD", "SKIP_DEL"}
    )
    # SKIP_DEL is in target but not source — should be skipped, not deleted
    assert "SKIP_DEL" in result.skipped
    assert "SKIP_DEL" not in result.deleted
    assert "SKIP_DEL" in target


# ── write_env_file: special character quoting ───────────────────────────────


def test_write_env_file_hash_in_value(tmp_path):
    """Values containing # should be double-quoted."""
    env_vars = {"KEY": "val#ue"}
    path = tmp_path / ".env"
    write_env_file(str(path), env_vars)
    content = path.read_text()
    assert 'KEY="val#ue"' in content


def test_write_env_file_quote_in_value(tmp_path):
    """Values containing double quotes should be escaped and quoted."""
    env_vars = {"KEY": 'val"ue'}
    path = tmp_path / ".env"
    write_env_file(str(path), env_vars)
    content = path.read_text()
    assert 'KEY="val\\"ue"' in content


def test_write_env_file_backslash_in_value(tmp_path):
    """Backslashes should be escaped in quoted values."""
    env_vars = {"KEY": r"path\to\file"}
    path = tmp_path / ".env"
    write_env_file(str(path), env_vars)
    content = path.read_text()
    # The value contains backslashes which trigger quoting; backslashes are doubled
    assert "path\\to\\file" in content or "path\\\\to\\\\file" in content


def test_write_env_file_space_in_value(tmp_path):
    """Values with spaces should be quoted."""
    env_vars = {"KEY": "hello world"}
    path = tmp_path / ".env"
    write_env_file(str(path), env_vars)
    content = path.read_text()
    assert 'KEY="hello world"' in content


def test_write_env_file_newline_in_value(tmp_path):
    """Values with newlines should be quoted."""
    env_vars = {"KEY": "line1\nline2"}
    path = tmp_path / ".env"
    write_env_file(str(path), env_vars)
    content = path.read_text()
    assert 'KEY="line1\\nline2"' in content or 'KEY="line1\nline2"' in content


def test_write_env_file_plain_value(tmp_path):
    """Values without special chars should NOT be quoted."""
    env_vars = {"KEY": "simple123"}
    path = tmp_path / ".env"
    write_env_file(str(path), env_vars)
    content = path.read_text()
    assert "KEY=simple123" in content
    assert 'KEY="simple123"' not in content


def test_write_env_file_creates_parent_dirs(tmp_path):
    """write_env_file should create parent directories if they don't exist."""
    path = tmp_path / "subdir" / "nested" / ".env"
    write_env_file(str(path), {"KEY": "val"})
    assert path.exists()
    assert "KEY=val" in path.read_text()


# ── sync_env_files: audit logging ──────────────────────────────────────────


def test_sync_env_files_audit_add(tmp_path):
    """Audit logger should log 'add' actions for added keys."""
    src = tmp_path / ".env.dev"
    tgt = tmp_path / ".env.prod"
    src.write_text("NEW_KEY=from_dev\n")
    tgt.write_text("EXISTING=old\n")

    audit_log = str(tmp_path / "audit.log")
    audit = AuditLogger(audit_log)

    result = sync_env_files(str(src), str(tgt), audit=audit)
    assert "NEW_KEY" in result.added

    history = audit.get_history(action="add")
    assert len(history) >= 1
    assert any(h["key"] == "NEW_KEY" for h in history)


def test_sync_env_files_audit_update(tmp_path):
    """Audit logger should log 'update' actions for updated keys."""
    src = tmp_path / ".env.dev"
    tgt = tmp_path / ".env.prod"
    src.write_text("KEY=new_val\n")
    tgt.write_text("KEY=old_val\n")

    audit_log = str(tmp_path / "audit.log")
    audit = AuditLogger(audit_log)

    result = sync_env_files(str(src), str(tgt), audit=audit)
    assert "KEY" in result.updated

    history = audit.get_history(action="update")
    assert len(history) >= 1
    assert any(h["key"] == "KEY" for h in history)


def test_sync_env_files_audit_delete(tmp_path):
    """Audit logger should log 'delete' actions for removed keys."""
    src = tmp_path / ".env.dev"
    tgt = tmp_path / ".env.prod"
    src.write_text("KEY=shared\n")
    tgt.write_text("KEY=shared\nOLD_KEY=remove\n")

    audit_log = str(tmp_path / "audit.log")
    audit = AuditLogger(audit_log)

    result = sync_env_files(str(src), str(tgt), allow_delete=True, audit=audit)
    assert "OLD_KEY" in result.deleted

    history = audit.get_history(action="delete")
    assert len(history) >= 1
    assert any(h["key"] == "OLD_KEY" for h in history)


def test_sync_env_files_no_audit_when_no_changes(tmp_path):
    """When source and target are already in sync, no audit entries should be written."""
    src = tmp_path / ".env.dev"
    tgt = tmp_path / ".env.prod"
    src.write_text("KEY=val\n")
    tgt.write_text("KEY=val\n")

    audit_log = str(tmp_path / "audit.log")
    audit = AuditLogger(audit_log)

    sync_env_files(str(src), str(tgt), audit=audit)
    assert len(audit.get_history()) == 0
