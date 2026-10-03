"""Tests for backup manifest loading resilience."""

from __future__ import annotations

import json
from pathlib import Path

from envault.backup import BACKUP_MANIFEST, _load_manifest


def _write_manifest(backup_dir: Path, data: list[dict]) -> None:
    """Helper to write raw manifest JSON."""
    manifest_path = backup_dir / BACKUP_MANIFEST
    manifest_path.write_text(json.dumps(data), encoding="utf-8")


def test_load_manifest_skips_corrupt_entries(tmp_path: Path) -> None:
    """A single corrupt entry must not discard valid entries.

    Regression: previously a KeyError on any entry caused the entire
    manifest to be silently discarded, losing all valid backups.
    """
    valid_entry = {
        "name": "good-backup",
        "source_file": ".env",
        "backup_path": str(tmp_path / "good-backup"),
        "timestamp": "2026-08-10T00:00:00+00:00",
        "encrypted": False,
    }
    corrupt_entry = {"name": "missing-fields"}  # missing source_file, backup_path, timestamp

    _write_manifest(tmp_path, [valid_entry, corrupt_entry])

    entries = _load_manifest(tmp_path)

    assert len(entries) == 1
    assert entries[0].name == "good-backup"
    assert entries[0].source_file == ".env"


def test_load_manifest_all_corrupt_returns_empty(tmp_path: Path) -> None:
    """When every entry is corrupt, return empty list without raising."""
    _write_manifest(tmp_path, [{"bad": True}, {"also_bad": True}])

    entries = _load_manifest(tmp_path)

    assert entries == []


def test_load_manifest_valid_json_but_not_list(tmp_path: Path) -> None:
    """A manifest that is valid JSON but not a list returns empty."""
    manifest_path = tmp_path / BACKUP_MANIFEST
    manifest_path.write_text('{"not": "a list"}', encoding="utf-8")

    entries = _load_manifest(tmp_path)

    assert entries == []


def test_load_manifest_preserves_order(tmp_path: Path) -> None:
    """Valid entries are returned in their original order."""
    entries_data = [
        {
            "name": f"backup-{i}",
            "source_file": f".env.{i}",
            "backup_path": str(tmp_path / f"backup-{i}"),
            "timestamp": f"2026-08-10T00:0{i}:00+00:00",
            "encrypted": False,
        }
        for i in range(5)
    ]
    # Insert a corrupt entry in the middle
    entries_data.insert(2, {"corrupt": True})

    _write_manifest(tmp_path, entries_data)

    result = _load_manifest(tmp_path)

    assert len(result) == 5
    assert [e.name for e in result] == [f"backup-{i}" for i in range(5)]
