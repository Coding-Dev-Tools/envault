"""Tests for git-based .env change history (src/envault/history.py)."""

from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from envault.history import (
    EnvFileHistory,
    _get_commit_meta,
    _mask_value,
    _parse_env_content,
    get_env_history,
)

GIT_AVAILABLE = shutil.which("git") is not None


# ── _parse_env_content ────────────────────────────────────────────────────


def test_parse_env_content_basic():
    content = "A=1\nB = two\n\n# comment\nNO_EQUALS_LINE\n"
    parsed = _parse_env_content(content)
    assert parsed == {"A": "1", "B": "two"}


def test_parse_env_content_strips_symmetric_quotes():
    content = 'A="quoted"\nB=' + "'single'\n" + "C=un\"matched\n"
    parsed = _parse_env_content(content)
    assert parsed["A"] == "quoted"
    assert parsed["B"] == "single"
    assert parsed["C"] == 'un"matched'


# ── _get_commit_meta ──────────────────────────────────────────────────────


def test_commit_meta_survives_pipe_in_author(monkeypatch):
    """An author name containing '|' must not silently drop the metadata."""
    payload = "Jane | Doe\x002026-01-02 03:04:05 +0000\x00rotate staging keys\n"

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    meta = _get_commit_meta("abc123")
    assert meta == {
        "author": "Jane | Doe",
        "date": "2026-01-02 03:04:05 +0000",
        "message": "rotate staging keys",
    }


def test_commit_meta_subject_with_pipes(monkeypatch):
    """Only the FIRST two separators split; the subject keeps any '|'.

    The legacy '|' delimiter truncated subjects at the first pipe.
    """
    payload = "auth\x00date\x00fix: a | b | c\n"

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    meta = _get_commit_meta("abc123")
    assert meta is not None
    assert meta["message"] == "fix: a | b | c"


def test_commit_meta_git_failure_returns_none(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _get_commit_meta("deadbeef") is None


# ── _mask_value ───────────────────────────────────────────────────────────


def test_mask_value_long_secret_is_masked():
    masked = _mask_value("supersecretvalue_0123456789")
    assert masked.startswith("supersec")
    assert "..." in masked
    assert "0123456789" not in masked


def test_mask_value_short_or_pathlike_kept():
    assert _mask_value("short") == "short"
    assert _mask_value("/usr/local/bin") == "/usr/local/bin"


# ── end-to-end against a real temp repo ───────────────────────────────────


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git not available")
def test_get_env_history_detects_changes_in_nested_file(tmp_path):
    """Regression: nested paths must be passed to git with '/' separators.

    Windows backslash pathspecs matched nothing, so history came back empty
    (silent failure) for every .env file not at the repo root.
    """
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")

    nested = tmp_path / "config"
    nested.mkdir()
    env_file = nested / ".env"
    env_file.write_text("A=1\nB=keep\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    env_file.write_text("A=2\nB=keep\nC=new\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "update values")

    history = get_env_history(env_file)
    assert isinstance(history, EnvFileHistory)
    actions = {(c.key, c.action) for c in history.changes}
    assert ("A", "changed") in actions
    assert ("C", "added") in actions
    # Unchanged key may only be recorded once, as the initial-commit add.
    b_actions = [c.action for c in history.changes if c.key == "B"]
    assert b_actions == ["added"]


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git not available")
def test_get_env_history_key_filter(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")

    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    env_file.write_text("A=2\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "change a")

    history = get_env_history(env_file, key_filter="A")
    assert history.total_changes >= 1
    assert all(c.key == "A" for c in history.changes)
