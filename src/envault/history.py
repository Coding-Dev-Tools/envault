"""Git-based change history tracking for .env files."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class EnvChange:
    """A single change to an .env file recorded in git history."""

    commit: str
    author: str
    date: str
    message: str
    key: str
    action: str  # "added", "removed", "changed"
    old_value: str | None = None
    new_value: str | None = None


@dataclass
class EnvFileHistory:
    """Change history for a single .env file."""

    file_path: str
    changes: list[EnvChange] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.changes)

    def to_dict(self, mask_values: bool = True) -> dict:
        """Serialize history as a dict suitable for JSON output."""
        mask = _mask_value if mask_values else lambda v: v
        return {
            "file": self.file_path,
            "total_changes": self.total_changes,
            "changes": [
                {
                    "commit": c.commit,
                    "author": c.author,
                    "date": c.date,
                    "message": c.message,
                    "key": c.key,
                    "action": c.action,
                    "old_value": mask(c.old_value) if c.old_value is not None else None,
                    "new_value": mask(c.new_value) if c.new_value is not None else None,
                }
                for c in self.changes
            ],
        }

    def to_json(self, mask_values: bool = True, indent: int | None = 2) -> str:
        """Serialize history as a JSON string."""
        return json.dumps(self.to_dict(mask_values=mask_values), indent=indent)


def get_env_history(
    file_path: str | Path,
    *,
    max_commits: int = 50,
    key_filter: str | None = None,
) -> EnvFileHistory:
    """Get the change history of an .env file from git.

    Walks git log for the given file, parses each commit's diff,
    and categorises changes as added/removed/changed per key.

    Args:
        file_path: Path to the .env file to track.
        max_commits: Maximum number of git commits to inspect.
        key_filter: If set, only return changes for this key.

    Returns:
        EnvFileHistory with all detected changes.
    """
    file_path = Path(file_path)
    history = EnvFileHistory(file_path=str(file_path))

    # Verify we're in a git repo
    if not _is_git_repo(file_path):
        return history

    # Get list of commits that touched this file
    commits = _get_commits_for_file(file_path, max_commits=max_commits)
    if not commits:
        return history

    # For each consecutive pair of commits, diff the file content
    for i in range(len(commits)):
        commit = commits[i]
        parent_ref = commits[i + 1] if i + 1 < len(commits) else f"{commit}^"

        changes = _diff_at_commit(file_path, commit, parent_ref)
        for change in changes:
            if key_filter and change.key != key_filter:
                continue
            history.changes.append(change)

    return history


def get_env_history_multiple(
    file_paths: list[str | Path],
    *,
    max_commits: int = 50,
    key_filter: str | None = None,
) -> list[EnvFileHistory]:
    """Get change history for multiple .env files.

    Args:
        file_paths: List of .env file paths.
        max_commits: Maximum commits per file.
        key_filter: Optional key to filter on.

    Returns:
        List of EnvFileHistory, one per file.
    """
    return [
        get_env_history(fp, max_commits=max_commits, key_filter=key_filter)
        for fp in file_paths
    ]


def format_history(history: EnvFileHistory, *, verbose: bool = False) -> str:
    """Format an EnvFileHistory as a human-readable string.

    Args:
        history: The history to format.
        verbose: If True, include values in the output.
    """
    lines: list[str] = []

    if not history.changes:
        lines.append(f"No git history found for {history.file_path}")
        return "\n".join(lines)

    lines.append(f"Change history for {history.file_path} ({history.total_changes} changes)")
    lines.append("")

    for change in history.changes:
        short_commit = change.commit[:7]
        action_symbol = {"added": "+", "removed": "-", "changed": "~"}.get(change.action, "?")
        lines.append(f"  {action_symbol} {change.key}  ({change.action})")

        if verbose:
            if change.old_value is not None:
                lines.append(f"    old: {change.old_value}")
            if change.new_value is not None:
                lines.append(f"    new: {change.new_value}")

        lines.append(f"    {short_commit} by {change.author} — {change.date}")
        lines.append(f"    {change.message}")

    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────


def _is_git_repo(file_path: Path) -> bool:
    """Check if the file is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=file_path.parent if file_path.parent.exists() else ".",
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_commits_for_file(file_path: Path, *, max_commits: int = 50) -> list[str]:
    """Return a list of commit hashes that touched the given file, newest first."""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={max_commits}", "--format=%H", "--", str(file_path)],
            capture_output=True,
            text=True,
            cwd=file_path.parent if file_path.parent.exists() else ".",
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _diff_at_commit(
    file_path: Path,
    commit: str,
    parent_ref: str,
) -> list[EnvChange]:
    """Get the diff for a single file at a given commit vs its parent.

    Returns a list of EnvChange entries for each key that was added, removed,
    or changed.
    """
    # Get commit metadata
    meta = _get_commit_meta(commit)
    if meta is None:
        return []

    # Get the diff content for this file at this commit
    diff_text = _get_file_diff(file_path, commit, parent_ref)

    # Parse the unified diff to extract key-level changes
    old_content = _get_file_at_ref(file_path, parent_ref)
    new_content = _get_file_at_ref(file_path, commit)

    old_vars = _parse_env_content(old_content)
    new_vars = _parse_env_content(new_content)

    changes: list[EnvChange] = []

    old_keys = set(old_vars.keys())
    new_keys = set(new_vars.keys())

    # Added keys
    for key in sorted(new_keys - old_keys):
        changes.append(EnvChange(
            commit=commit,
            author=meta["author"],
            date=meta["date"],
            message=meta["message"],
            key=key,
            action="added",
            old_value=None,
            new_value=new_vars[key],
        ))

    # Removed keys
    for key in sorted(old_keys - new_keys):
        changes.append(EnvChange(
            commit=commit,
            author=meta["author"],
            date=meta["date"],
            message=meta["message"],
            key=key,
            action="removed",
            old_value=old_vars[key],
            new_value=None,
        ))

    # Changed values
    for key in sorted(old_keys & new_keys):
        if old_vars[key] != new_vars[key]:
            changes.append(EnvChange(
                commit=commit,
                author=meta["author"],
                date=meta["date"],
                message=meta["message"],
                key=key,
                action="changed",
                old_value=old_vars[key],
                new_value=new_vars[key],
            ))

    return changes


def _get_commit_meta(commit: str) -> dict | None:
    """Get author, date, and message for a commit."""
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%an|%ai|%s", commit],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split("|", 2)
        if len(parts) != 3:
            return None
        return {"author": parts[0], "date": parts[1], "message": parts[2]}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _get_file_at_ref(file_path: Path, ref: str) -> str:
    """Get the content of a file at a given git ref (commit, tree-ish)."""
    try:
        # Use relative path from git root for git show
        rel_path = _get_relative_path(file_path)
        result = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            capture_output=True,
            text=True,
            cwd=file_path.parent if file_path.parent.exists() else ".",
            timeout=10,
        )
        if result.returncode != 0:
            return ""
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _get_file_diff(file_path: Path, commit: str, parent_ref: str) -> str:
    """Get the unified diff for a file between parent and commit."""
    try:
        rel_path = _get_relative_path(file_path)
        result = subprocess.run(
            ["git", "diff", parent_ref, commit, "--", rel_path],
            capture_output=True,
            text=True,
            cwd=file_path.parent if file_path.parent.exists() else ".",
            timeout=10,
        )
        if result.returncode != 0:
            return ""
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _get_relative_path(file_path: Path) -> str:
    """Get the git-relative path for a file."""
    try:
        abs_path = file_path.resolve()
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=file_path.parent if file_path.parent.exists() else ".",
            timeout=10,
        )
        if result.returncode == 0:
            repo_root = Path(result.stdout.strip())
            try:
                return str(abs_path.relative_to(repo_root))
            except ValueError:
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return file_path.name


def _parse_env_content(content: str) -> dict[str, str]:
    """Parse .env file content into a key-value dict.

    Simple parser that handles KEY=VALUE lines, ignoring comments and blanks.
    """
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def _mask_value(value: str, max_show: int = 8) -> str:
    """Mask sensitive values, showing only first few chars if they look like secrets."""
    if len(value) > 16 and not value.startswith("/") and not value.replace(".", "").replace("-", "").isdigit():
        return value[:max_show] + "..." + value[-4:]
    return value
