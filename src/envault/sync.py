"""Environment variable syncing engine for Envault."""

from __future__ import annotations

from pathlib import Path

from .audit import AuditLogger
from .diff import load_env_file


class SyncConflict(Exception):
    """Raised when a sync conflict cannot be auto-resolved."""
    def __init__(self, key: str, source_value: str, target_value: str):
        self.key = key
        self.source_value = source_value
        self.target_value = target_value
        super().__init__(f"Conflict on '{key}': source='{source_value[:20]}...' vs target='{target_value[:20]}...'")


class SyncResult:
    """Result of an environment sync operation."""

    def __init__(self):
        self.added: list[str] = []
        self.updated: list[str] = []
        self.deleted: list[str] = []
        self.conflicts: list[SyncConflict] = []
        self.skipped: list[str] = []

    @property
    def success_count(self) -> int:
        return len(self.added) + len(self.updated)

    def __str__(self) -> str:
        parts = []
        if self.added:
            parts.append(f"+ {len(self.added)} added")
        if self.updated:
            parts.append(f"~ {len(self.updated)} updated")
        if self.deleted:
            parts.append(f"- {len(self.deleted)} deleted")
        if self.conflicts:
            parts.append(f"! {len(self.conflicts)} conflicts")
        if self.skipped:
            parts.append(f"- {len(self.skipped)} skipped")
        return ", ".join(parts) if parts else "No changes"


def sync_envs(
    source: dict[str, str],
    target: dict[str, str],
    *,
    strategy: str = "source_wins",
    allow_delete: bool = False,
    skip_keys: set[str] | None = None,
) -> SyncResult:
    """Sync environment variables from source to target.

    Args:
        source: Source environment variables.
        target: Target environment variables (will be modified in-place).
        strategy: Conflict resolution strategy:
            - "source_wins": source overrides target on conflict
            - "target_wins": target values are preserved
            - "error": raise on conflict
        allow_delete: If True, keys in target but not in source will be removed.
        skip_keys: Set of keys to skip during sync.

    Returns:
        SyncResult describing what happened.
    """
    result = SyncResult()
    skip_keys = skip_keys or set()

    source_keys = set(source.keys())
    target_keys = set(target.keys())

    # Keys to add (in source but not in target)
    for k in sorted(source_keys - target_keys):
        if k in skip_keys:
            result.skipped.append(k)
            continue
        target[k] = source[k]
        result.added.append(k)

    # Keys to update (in both but different)
    common_keys = source_keys & target_keys
    for k in sorted(common_keys):
        if k in skip_keys:
            result.skipped.append(k)
            continue
        if source[k] != target[k]:
            if strategy == "target_wins":
                # Keep target value, mark as skipped
                result.skipped.append(k)
            elif strategy == "error":
                raise SyncConflict(k, source[k], target[k])
            else:  # source_wins
                target[k] = source[k]
                result.updated.append(k)

    # Keys to delete (in target but not in source)
    if allow_delete:
        for k in sorted(target_keys - source_keys):
            if k in skip_keys:
                result.skipped.append(k)
                continue
            del target[k]
            result.deleted.append(k)

    return result


def write_env_file(path: str | Path, env_vars: dict[str, str]) -> int:
    """Write environment variables to a .env file.

    Returns the number of variables written.
    """
    path = Path(path)
    lines: list[str] = []
    for key, value in sorted(env_vars.items()):
        # Quote values with special characters
        if any(c in value for c in " #'\"\n\t"):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return len(lines)


def sync_env_files(
    source_path: str | Path,
    target_path: str | Path,
    *,
    strategy: str = "source_wins",
    allow_delete: bool = False,
    skip_keys: set[str] | None = None,
    audit: AuditLogger | None = None,
) -> SyncResult:
    """Sync environment variables from one .env file to another.

    Args:
        source_path: Source .env file path.
        target_path: Target .env file path.
        strategy: Conflict resolution strategy.
        allow_delete: If True, remove keys in target not in source.
        skip_keys: Set of keys to skip.
        audit: Optional audit logger.

    Returns:
        SyncResult describing what happened.
    """
    source = load_env_file(source_path)
    target = load_env_file(target_path)

    result = sync_envs(
        source, target,
        strategy=strategy,
        allow_delete=allow_delete,
        skip_keys=skip_keys,
    )

    if result.success_count > 0 or result.deleted:
        write_env_file(target_path, target)
        if audit:
            for k in result.added:
                audit.log("add", k, source_path=str(source_path), target_path=str(target_path))
            for k in result.updated:
                audit.log("update", k, source_path=str(source_path), target_path=str(target_path))
            for k in result.deleted:
                audit.log("delete", k, target_path=str(target_path))

    return result
