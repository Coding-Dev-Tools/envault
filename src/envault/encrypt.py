"""Encrypt and decrypt .env files using Fernet symmetric encryption.

Usage:
    envault encrypt .env           # Encrypt .env -> .env.locked
    envault decrypt .env.locked    # Decrypt .env.locked -> .env

The encryption key is derived from a master password via PBKDF2.
Key can also be stored in REVENUEHOLDINGS_LICENSE_KEY env var or
passed via --key flag for CI/CD.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import os
import sys
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ── Constants ────────────────────────────────────────────────────────────────

SALT_FILE = ".envault.salt"
LOCKED_SUFFIX = ".locked"
ENCRYPTED_HEADER = "# Encrypted by Envault — do not edit manually\n"
PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation

# Env var that can hold the encryption key (for CI/CD)
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


def _get_or_create_salt(salt_path: Path) -> bytes:
    """Load existing salt or create a new one."""
    if salt_path.exists():
        return salt_path.read_bytes()
    salt = os.urandom(16)
    salt_path.write_bytes(salt)
    return salt


def _get_password(prompt: str = "Encryption password: ") -> str:
    """Get password from user or env var."""
    env_key = os.environ.get(KEY_ENV_VAR)
    if env_key:
        return env_key
    return getpass.getpass(prompt)


# ── Encrypt / Decrypt ───────────────────────────────────────────────────────


def encrypt_env(
    input_path: Path,
    output_path: Optional[Path] = None,
    password: Optional[str] = None,
    delete_original: bool = False,
) -> Path:
    """Encrypt a .env file.

    Args:
        input_path: Path to the .env file to encrypt.
        output_path: Output path (default: input_path + .locked).
        password: Encryption password (prompted if None).
        delete_original: Delete the original file after encryption.

    Returns:
        Path to the encrypted file.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    content = input_path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"File is empty: {input_path}")

    if password is None:
        password = _get_password()

    salt_path = input_path.parent / SALT_FILE
    salt = _get_or_create_salt(salt_path)
    key = _derive_key(password, salt)
    fernet = Fernet(key)

    encrypted = fernet.encrypt(content.encode("utf-8"))
    output = output_path or input_path.with_suffix(input_path.suffix + LOCKED_SUFFIX)
    output.write_bytes(encrypted)

    if delete_original and output.exists():
        input_path.unlink()

    return output


def decrypt_env(
    input_path: Path,
    output_path: Optional[Path] = None,
    password: Optional[str] = None,
    delete_encrypted: bool = False,
) -> Path:
    """Decrypt a .env.locked file.

    Args:
        input_path: Path to the encrypted file.
        output_path: Output path (default: strip .locked suffix).
        password: Decryption password (prompted if None).
        delete_encrypted: Delete the encrypted file after decryption.

    Returns:
        Path to the decrypted file.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    if password is None:
        password = _get_password("Decryption password: ")

    salt_path = input_path.parent / SALT_FILE
    if not salt_path.exists():
        raise FileNotFoundError(
            f"Salt file not found: {salt_path}. "
            "Cannot decrypt without the original salt."
        )

    salt = salt_path.read_bytes()
    key = _derive_key(password, salt)
    fernet = Fernet(key)

    encrypted_data = input_path.read_bytes()
    try:
        decrypted = fernet.decrypt(encrypted_data)
    except Exception as e:
        raise ValueError(f"Decryption failed (wrong password?): {e}") from e

    # Determine output path
    if output_path is None:
        # Strip .locked suffix
        stem = input_path.stem
        if stem.endswith(LOCKED_SUFFIX.replace(".", "")):
            stem = stem[: -len(LOCKED_SUFFIX.replace(".", ""))]
        output_path = input_path.with_stem(stem).with_suffix("")  # e.g. .env

    output_path.write_bytes(decrypted)

    if delete_encrypted and output_path.exists():
        input_path.unlink()

    return output_path


def is_encrypted(file_path: Path) -> bool:
    """Check if a file looks like an envault-encrypted file."""
    if not file_path.exists():
        return False
    try:
        data = file_path.read_bytes()
        # Fernet tokens are base64-encoded and start with gAAAA by default
        return data.startswith(b"gAAAA") or file_path.suffix == LOCKED_SUFFIX
    except Exception:
        return False
