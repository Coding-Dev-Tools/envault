"""Secret rotation engine for Envault."""

from __future__ import annotations

import os
import secrets
import string
from pathlib import Path

from .audit import AuditLogger


def generate_secret(
    length: int = 32,
    *,
    use_upper: bool = True,
    use_lower: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    exclude_chars: str = "",
) -> str:
    """Generate a cryptographically random secret.

    Args:
        length: Length of the secret.
        use_upper: Include uppercase letters.
        use_lower: Include lowercase letters.
        use_digits: Include digits.
        use_symbols: Include special characters.
        exclude_chars: Characters to exclude.

    Returns:
        A random secret string.
    """
    chars = ""
    if use_upper:
        chars += string.ascii_uppercase
    if use_lower:
        chars += string.ascii_lowercase
    if use_digits:
        chars += string.digits
    if use_symbols:
        chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"

    for c in exclude_chars:
        chars = chars.replace(c, "")

    if not chars:
        chars = string.ascii_letters + string.digits

    return "".join(secrets.choice(chars) for _ in range(length))


def generate_db_password() -> str:
    """Generate a secure database password (no ambiguous chars)."""
    return generate_secret(24, use_symbols=False, exclude_chars="Il1O0")


def generate_api_key(prefix: str = "ev_") -> str:
    """Generate an API key with a prefix."""
    return prefix + generate_secret(40, use_symbols=False)


def generate_jwt_secret() -> str:
    """Generate a 256-bit JWT secret (base64-encoded 32 bytes)."""
    import base64

    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def rotate_value(
    key: str,
    current_value: str,
    *,
    length: int = 32,
    store_type: str = "env",
) -> str:
    """Rotate a secret value, generating an appropriate replacement.

    Args:
        key: The env var name (used to infer type).
        current_value: The current value (for reference).
        length: Desired length.
        store_type: Type of store ('env', 'aws-ssm', 'vault', etc.).

    Returns:
        A new generated secret value.
    """
    key_lower = key.lower()

    # Database passwords
    if any(db_kw in key_lower for db_kw in ["db_", "database", "dbpassword", "db_pass"]):
        return generate_db_password()

    # API keys
    if any(api_kw in key_lower for api_kw in ["api_key", "apikey", "api_secret", "apisecret"]):
        prefix = key.split("_")[0].lower()[:4] + "_"
        return generate_api_key(prefix=prefix)

    # JWT secrets
    if any(jwt_kw in key_lower for jwt_kw in ["jwt", "jwt_secret", "jwtsecret"]):
        return generate_jwt_secret()

    # Webhook secrets
    if "webhook" in key_lower:
        return generate_secret(48, use_symbols=False)

    # Default: standard secret
    return generate_secret(length)


def rotate_env_var(
    key: str,
    env_file: str | Path,
    *,
    length: int = 32,
    dry_run: bool = False,
    audit: AuditLogger | None = None,
) -> tuple[bool, str]:
    """Rotate a single environment variable in a .env file.

    Args:
        key: The env var name to rotate.
        env_file: Path to the .env file.
        length: Length of new secret.
        dry_run: If True, don't actually modify the file.
        audit: Optional audit logger.

    Returns:
        Tuple of (success, new_value).
    """
    from dotenv import dotenv_values

    env_file = Path(env_file)
    if not env_file.exists():
        return False, ""

    env_vars = dotenv_values(env_file)

    if key not in env_vars:
        return False, ""

    current_value = env_vars[key]
    if current_value is None:
        return False, ""
    new_value = rotate_value(key, current_value, length=length)

    if dry_run:
        return True, new_value

    # Read file, replace the value for this key
    with open(env_file) as f:
        content = f.read()

    import re

    # Match KEY=value or KEY="..." or KEY='...' — anchored to full value
    pattern = re.compile(
        rf"^{re.escape(key)}\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\n]*)$",
        re.MULTILINE,
    )

    # Escape new value for the .env file
    if any(c in new_value for c in " #'\"\n\t"):
        escaped = new_value.replace("\\", "\\\\").replace('"', '\\"')
        replacement = f'{key}="{escaped}"'
    else:
        replacement = f"{key}={new_value}"

    new_content = pattern.sub(replacement, content)

    with open(env_file, "w") as f:
        f.write(new_content)

    if audit:
        audit.log("rotate", key, env_file=str(env_file))

    return True, new_value
