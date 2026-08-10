"""Backup .env files with optional encryption.

Usage:
    envault backup --env dev          # Backup dev env to .envault-backups/
    envault backup --all              # Backup all configured envs
    envault backup --file .env        # Backup a specific file
    envault backup --env dev --encrypt  # Backup with encryption
    envault backup --list             # List existing backups
    envault backup --restore <name>   # Restore a backup
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BACKUP_DIR = ".envault-backups"
BACKUP_MANIFEST = "manifest.json"


class BackupEntry:
    """Represents a single backup entry."""

    def __init__(
        self,
        name: str,
        source_file: str,
        backup_path: str,
        timestamp: str,
        encrypted: bool = False,
    ):
        self.name = name
        self.source_file = source_file
        self.backup_path = backup_path
        self.timestamp = timestamp
        self.encrypted = encrypted

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_file": self.source_file,
            "backup_path": self.backup_path,
            "timestamp": self.timestamp,
            "encrypted": self.encrypted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BackupEntry:
        return cls(
            name=data["name"],
            source_file=data["source_file"],
            backup_path=data["backup_path"],
            timestamp=data["timestamp"],
            encrypted=data.get("encrypted", False),
        )


class BackupResult:
    """Result of a backup operation."""

    def __init__(
        self,
        backups: list[BackupEntry] | None = None,
        errors: list[str] | None = None,
    ):
        self.backups = backups or []
        self.errors = errors or []

    @property
    def success_count(self) -> int:
        return len(self.backups)

    def to_dict(self) -> dict:
        return {
            "success_count": self.success_count,
            "error_count": len(self.errors),
            "backups": [b.to_dict() for b in self.backups],
            "errors": self.errors,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _get_backup_dir(project_dir: Path | str = ".") -> Path:
    """Get the backup directory path, creating it if needed."""
    backup_dir = Path(project_dir) / BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _load_manifest(backup_dir: Path) -> list[BackupEntry]:
    """Load the backup manifest from disk.

    Skips individual corrupt entries rather than discarding the entire
    manifest, preserving valid backups when one entry is malformed.
    """
    manifest_path = backup_dir / BACKUP_MANIFEST
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    entries: list[BackupEntry] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            entries.append(BackupEntry.from_dict(entry))
        except (KeyError, TypeError):
            continue
    return entries


def _save_manifest(backup_dir: Path, entries: list[BackupEntry]) -> None:
    """Save the backup manifest to disk."""
    manifest_path = backup_dir / BACKUP_MANIFEST
    data = [entry.to_dict() for entry in entries]
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _generate_backup_name(source_file: str) -> str:
    """Generate a unique backup name from the source file and timestamp."""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    stem = Path(source_file).name
    return f"{stem}.{ts}"


def backup_env_file(
    source_path: Path | str,
    project_dir: Path | str = ".",
    encrypt: bool = False,
    password: str | None = None,
) -> BackupEntry:
    """Back up a single .env file, optionally encrypting it.

    Args:
        source_path: Path to the .env file to back up.
        project_dir: Project directory (backup dir created inside).
        encrypt: Whether to encrypt the backup.
        password: Encryption password (prompted if None and encrypt=True).

    Returns:
        BackupEntry describing the backup.

    Raises:
        FileNotFoundError: If the source file does not exist.
    """
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")

    backup_dir = _get_backup_dir(project_dir)
    backup_name = _generate_backup_name(str(source_path))

    if encrypt:
        # Store encrypted backup with .locked suffix
        backup_file = backup_dir / (backup_name + ".locked")
        from envault.encrypt import encrypt_env

        encrypt_env(source_path, output_path=backup_file, password=password)
    else:
        backup_file = backup_dir / backup_name
        shutil.copy2(source_path, backup_file)

    now = datetime.now(timezone.utc).isoformat()
    entry = BackupEntry(
        name=backup_name,
        source_file=str(source_path),
        backup_path=str(backup_file),
        timestamp=now,
        encrypted=encrypt,
    )

    # Update manifest
    manifest = _load_manifest(backup_dir)
    manifest.append(entry)
    _save_manifest(backup_dir, manifest)

    return entry


def list_backups(
    project_dir: Path | str = ".",
) -> list[BackupEntry]:
    """List all existing backups.

    Args:
        project_dir: Project directory containing .envault-backups/.

    Returns:
        List of BackupEntry objects from the manifest.
    """
    backup_dir = Path(project_dir) / BACKUP_DIR
    if not backup_dir.exists():
        return []
    return _load_manifest(backup_dir)


def restore_backup(
    name: str,
    target_path: Path | str | None = None,
    project_dir: Path | str = ".",
    password: str | None = None,
) -> Path:
    """Restore a backup by name.

    Args:
        name: Backup name (from list_backups).
        target_path: Where to restore the file (defaults to original source path).
        project_dir: Project directory containing .envault-backups/.
        password: Decryption password (prompted if None and backup is encrypted).

    Returns:
        Path to the restored file.

    Raises:
        FileNotFoundError: If the backup does not exist.
        ValueError: If the backup name is not found in the manifest.
    """
    backup_dir = Path(project_dir) / BACKUP_DIR
    manifest = _load_manifest(backup_dir)

    entry = None
    for e in manifest:
        if e.name == name:
            entry = e
            break

    if entry is None:
        raise ValueError(f"Backup '{name}' not found in manifest")

    backup_file = Path(entry.backup_path)
    if not backup_file.exists():
        # Try relative to backup dir
        backup_file = backup_dir / backup_file.name
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    restore_path = Path(target_path) if target_path else Path(entry.source_file)

    if entry.encrypted:
        from envault.encrypt import decrypt_env

        decrypt_env(backup_file, output_path=restore_path, password=password)
    else:
        # Ensure parent directory exists
        restore_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, restore_path)

    return restore_path


def format_backup_list(entries: list[BackupEntry]) -> str:
    """Format a list of backups for display."""
    if not entries:
        return "No backups found."

    lines = []
    for entry in entries:
        enc_tag = " [encrypted]" if entry.encrypted else ""
        lines.append(f"  {entry.name}{enc_tag}\n    Source: {entry.source_file}\n    Created: {entry.timestamp}")
    return "\n".join(lines)
