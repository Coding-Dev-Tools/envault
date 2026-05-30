"""Backup .env files with encryption for Envault.

Bundles one or more .env files into a single encrypted archive.
Uses Fernet symmetric encryption (same as envault encrypt).
"""
from __future__ import annotations

import base64
import getpass
import json
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from datetime import datetime, timezone
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

BACKUP_SUFFIX = ".envault.bak"
BACKUP_MANIFEST_KEY = "__envault_backup_manifest__"
PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation
KEY_ENV_VAR = "ENVAULT_ENCRYPT_KEY"


# ── Key derivation ───────────────────────────────────────────────────────────


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet key from password + salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


def _get_password(prompt: str = "Encryption password: ") -> str:
    """Get password from user or env var."""
    env_key = os.environ.get(KEY_ENV_VAR)
    if env_key:
        return env_key
    return getpass.getpass(prompt)


# ── Backup ───────────────────────────────────────────────────────────────────


def backup_env_files(
    env_files: list[Path],
    output_path: Path | None = None,
    password: str | None = None,
) -> Path:
    """Backup one or more .env files into an encrypted archive.

    The archive is a JSON bundle containing:
    - A manifest with metadata (timestamp, file list)
    - The content of each .env file

    The entire bundle is then Fernet-encrypted.

    Args:
        env_files: List of .env file paths to back up.
        output_path: Output path for the backup archive.
            Default: envault-backup-YYYYMMDD-HHMMSS.envault.bak
        password: Encryption password (prompted if None).

    Returns:
        Path to the encrypted backup file.

    Raises:
        FileNotFoundError: If any .env file does not exist.
        ValueError: If no .env files are provided.
    """
    if not env_files:
        raise ValueError("No .env files specified for backup")

    # Validate all files exist
    missing = [f for f in env_files if not f.exists()]
    if missing:
        raise FileNotFoundError(
            f"File(s) not found: {', '.join(str(f) for f in missing)}"
        )

    if password is None:
        password = _get_password("Backup encryption password: ")

    # Build the backup bundle
    manifest = {
        "version": "1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }
    bundle = {}

    for env_file in env_files:
        # Store only the filename to keep backups portable and avoid
        # absolute-path issues on restore to a different directory.
        name = env_file.name
        content = env_file.read_text(encoding="utf-8")
        manifest["files"].append({
            "path": name,
            "size": len(content.encode("utf-8")),
        })
        bundle[name] = content

    bundle[BACKUP_MANIFEST_KEY] = json.dumps(manifest, indent=2)

    # Encrypt the bundle
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    fernet = Fernet(key)

    bundle_json = json.dumps(bundle, indent=2)
    encrypted = fernet.encrypt(bundle_json.encode("utf-8"))

    # Output: 16 bytes salt + encrypted payload
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = Path(f"envault-backup-{ts}{BACKUP_SUFFIX}")

    output_path.write_bytes(salt + encrypted)

    return output_path


# ── Restore ──────────────────────────────────────────────────────────────────


def restore_env_files(
    backup_path: Path,
    output_dir: Path | None = None,
    password: str | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Restore .env files from an encrypted backup archive.

    Args:
        backup_path: Path to the .envault.bak backup file.
        output_dir: Directory to restore files into.
            Default: current working directory (restores to original paths).
        password: Decryption password (prompted if None).
        overwrite: Whether to overwrite existing files.

    Returns:
        List of restored file paths.

    Raises:
        FileNotFoundError: If backup file does not exist.
        ValueError: If decryption fails (wrong password or corrupt backup).
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    if password is None:
        password = _get_password("Backup decryption password: ")

    # Read salt (first 16 bytes) + encrypted payload
    data = backup_path.read_bytes()
    if len(data) < 17:  # 16 salt + at least 1 byte encrypted
        raise ValueError("Backup file is too small to be valid")

    salt = data[:16]
    encrypted = data[16:]

    key = _derive_key(password, salt)
    fernet = Fernet(key)

    try:
        bundle_json = fernet.decrypt(encrypted)
    except Exception as e:
        raise ValueError(f"Decryption failed (wrong password?): {e}") from e

    try:
        bundle = json.loads(bundle_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Backup file is corrupt: {e}") from e

    # Extract manifest
    manifest_json = bundle.pop(BACKUP_MANIFEST_KEY, None)
    manifest = json.loads(manifest_json) if manifest_json else {}

    # Restore each file
    restored: list[Path] = []
    base_dir = (output_dir or Path(".")).resolve()

    for name, content in bundle.items():
        # name should be a simple filename (no directory components)
        # Block any path traversal attempts
        target = base_dir / name
        try:
            target.resolve().relative_to(base_dir)
        except ValueError:
            raise ValueError(
                f"Backup contains path outside output directory: {name}"
            )

        if target.exists() and not overwrite:
            raise FileExistsError(
                f"File already exists (use --overwrite): {target}"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        restored.append(target)

    return restored
