"""Environment variable diffing engine for Envault."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values


def load_env_file(path: str | Path) -> dict[str, str]:
    """Load a .env file, returning a dict of key-value pairs."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")
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

    def to_dict(
        self,
        source_label: str = "source",
        target_label: str = "target",
        mask_values: bool = True,
    ) -> dict:
        """Return the diff result as a plain dict suitable for JSON serialisation.

        Args:
            source_label: Label for the source environment in the output.
            target_label: Label for the target environment in the output.
            mask_values: If True, long secret-like values are partially masked.
        """
        mask = _mask_value if mask_values else lambda v: v

        only_in_source = {k: mask(v) for k, v in sorted(self.only_in_source.items())}
        only_in_target = {k: mask(v) for k, v in sorted(self.only_in_target.items())}
        different: dict[str, dict[str, str]] = {}
        for k in sorted(self.different.keys()):
            src_val, tgt_val = self.different[k]
            different[k] = {
                source_label: mask(src_val),
                target_label: mask(tgt_val),
            }
        common_keys = sorted(self.common.keys()) if self.common else []

        return {
            "has_differences": self.has_differences,
            "total_differences": self.total_differences,
            "only_in_source": only_in_source,
            "only_in_target": only_in_target,
            "different": different,
            "common_keys": common_keys,
        }

    def to_json(
        self,
        source_label: str = "source",
        target_label: str = "target",
        mask_values: bool = True,
        indent: int | None = 2,
    ) -> str:
        """Return the diff result as a JSON string.

        Args:
            source_label: Label for the source environment in the output.
            target_label: Label for the target environment in the output.
            mask_values: If True, long secret-like values are partially masked.
            indent: JSON indentation level (default 2). Pass None for compact output.
        """
        return json.dumps(
            self.to_dict(source_label, target_label, mask_values),
            indent=indent,
        )


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
    """Compare two .env files and return the diff.

    Non-existent files are treated as empty environments instead of raising.
    """
    try:
        source = load_env_file(source_path)
    except FileNotFoundError:
        source = {}
    try:
        target = load_env_file(target_path)
    except FileNotFoundError:
        target = {}
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
    # Value is long and not obviously a path or number — likely a secret
    if len(value) > 16 and not value.startswith("/") and not value.replace(".", "").replace("-", "").isdigit():
        return value[:max_show] + "..." + value[-4:]
    return value
