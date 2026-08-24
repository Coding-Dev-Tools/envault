"""Tests for atomic single-pass rotation (rotate_env_file)."""

from pathlib import Path

from dotenv import dotenv_values

from envault.rotate import rotate_env_file


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / ".env"
    p.write_text(content)
    return p


def test_rotate_env_file_rotates_all_keys(tmp_path):
    env = _write(tmp_path, "DB_PASSWORD=old\nAPI_KEY=old\nNOTE=keepme\n")
    plan = rotate_env_file(env, exclude={"NOTE"})
    assert set(plan) == {"DB_PASSWORD", "API_KEY"}
    new = dotenv_values(env)
    assert new["DB_PASSWORD"] != "old" and new["DB_PASSWORD"]
    assert new["API_KEY"] != "old" and new["API_KEY"]
    assert new["NOTE"] == "keepme"


def test_rotate_env_file_dry_run_leaves_file_untouched(tmp_path):
    original = "DB_PASSWORD=old\nAPI_KEY=old\n"
    env = _write(tmp_path, original)
    plan = rotate_env_file(env, dry_run=True)
    assert set(plan) == {"DB_PASSWORD", "API_KEY"}
    assert env.read_text() == original


def test_rotate_env_file_exclude(tmp_path):
    env = _write(tmp_path, "DB_PASSWORD=old\nKEEP_ME=untouched\n")
    rotate_env_file(env, exclude={"KEEP_ME"})
    assert dotenv_values(env)["KEEP_ME"] == "untouched"


def test_rotate_env_file_single_rewrite_is_atomic(tmp_path):
    """No temp files left behind; content replaced via os.replace."""
    env = _write(tmp_path, "A=1\nB=2\nC=3\n")
    rotate_env_file(env)
    leftovers = list(tmp_path.glob(".*rotate-tmp-*"))
    assert leftovers == []
    # comments/blank lines preserved
    text = env.read_text()
    assert all(line.startswith(k + "=") for k, line in zip("ABC", text.splitlines(), strict=True))


def test_rotate_env_file_preserves_comments_and_order(tmp_path):
    env = _write(tmp_path, "# creds\nA=1\n\nB=2  # trailing comment\n")
    rotate_env_file(env)
    lines = env.read_text().splitlines()
    assert lines[0] == "# creds"
    assert lines[2] == ""
    assert lines[1].startswith("A=") and lines[3].startswith("B=")


def test_rotate_env_file_audit_entries(tmp_path):
    from envault.audit import AuditLogger

    log = tmp_path / "audit.log"
    env = _write(tmp_path, "A=1\nB=2\n")
    rotate_env_file(env, audit=AuditLogger(log))
    entries = [line for line in log.read_text().splitlines() if line]
    assert len(entries) == 2
