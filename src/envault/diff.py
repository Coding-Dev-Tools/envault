"""Environment variable diffing engine for Envault."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values


def load_env_file(path: str | Path) -> dict[str, str]:
    """Load a .env file, returning a dict of key-value pairs."""
    path = Path(path)
    if not path.exists():
        return {}
    return {k: v for k, v in dotenv_values(path).items() if k is not None and v is not None}


def load_env_content(content: str) -> dict[str, str]:
    """Load environment variables from a string content."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write(content)
        tmp = f.name
    try:
        return {k: v for k, v in dotenv_values(tmp).items() if k is not None and v is not None}
    finally:
        os.unlink(tmp)


class EnvDiffResult:
    """Result of comparing two environment configurations."""

    def __init__(
        self,
        only_in_source: dict[str, str],
        only_in_target: dict[str, str],
        different: dict[str, tuple[str, str]],
        common: dict[str, str],
    ):
        self.only_in_source = only_in_source
        self.only_in_target = only_in_target
        self.different = different
        self.common = common

    @property
    def total_differences(self) -> int:
        return len(self.only_in_source) + len(self.only_in_target) + len(self.different)

    @property
    def has_differences(self) -> bool:
        return self.total_differences > 0


def diff_envs(
    source: dict[str, str],
    target: dict[str, str],
) -> EnvDiffResult:
    """Compare two environment variable dictionaries and return the diff.

    Args:
        source: The source environment variables.
        target: The target environment variables.

    Returns:
        EnvDiffResult with categorized differences.
    """
    source_keys = set(source.keys())
    target_keys = set(target.keys())

    only_in_source = {k: source[k] for k in (source_keys - target_keys)}
    only_in_target = {k: target[k] for k in (target_keys - source_keys)}
    common_keys = source_keys & target_keys

    different: dict[str, tuple[str, str]] = {}
    common: dict[str, str] = {}
    for k in common_keys:
        if source[k] != target[k]:
            different[k] = (source[k], target[k])
        else:
            common[k] = source[k]

    return EnvDiffResult(
        only_in_source=only_in_source,
        only_in_target=only_in_target,
        different=different,
        common=common,
    )


def diff_env_files(
    source_path: str | Path,
    target_path: str | Path,
) -> EnvDiffResult:
    """Compare two .env files and return the diff."""
    source = load_env_file(source_path)
    target = load_env_file(target_path)
    return diff_envs(source, target)


def format_diff(
    result: EnvDiffResult,
    source_label: str = "source",
    target_label: str = "target",
) -> str:
    """Format a diff result as a human-readable string."""
    lines: list[str] = []

    if not result.has_differences:
        return f"✓ Environments are identical ({len(result.common)} keys match)"

    if result.only_in_source:
        lines.append(f"\n--- Only in {source_label} ({len(result.only_in_source)}):")
        for k in sorted(result.only_in_source.keys()):
            lines.append(f"  + {k}={_mask_value(result.only_in_source[k])}")

    if result.only_in_target:
        lines.append(f"\n--- Only in {target_label} ({len(result.only_in_target)}):")
        for k in sorted(result.only_in_target.keys()):
            lines.append(f"  - {k}={_mask_value(result.only_in_target[k])}")

    if result.different:
        lines.append(f"\n--- Differing values ({len(result.different)}):")
        for k in sorted(result.different.keys()):
            src_val, tgt_val = result.different[k]
            lines.append(f"  ~ {k}:")
            lines.append(f"      {source_label}: {_mask_value(src_val)}")
            lines.append(f"      {target_label}: {_mask_value(tgt_val)}")

    if result.common:
        lines.append(f"\n--- Unchanged ({len(result.common)} keys)")

    return "\n".join(lines)


def _mask_value(value: str, max_show: int = 8) -> str:
    """Mask sensitive values, showing only first few chars if they look like secrets."""
    # Heuristic: if it looks like a key/secret/token, mask it
    common_secret_keys = ["key", "secret", "token", "password", "passwd", "auth", "api"]
    # Value is long and not obviously a path or number — likely a secret
    if len(value) > 16 and not value.startswith("/") and not value.replace(".", "").replace("-", "").isdigit():
        return value[:max_show] + "..." + value[-4:]
    return value
