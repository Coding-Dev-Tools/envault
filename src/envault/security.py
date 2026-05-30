"""Security audit engine for Envault — scans .env files for common security issues."""

from __future__ import annotations

import platform
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

# ── Issue severity levels ─────────────────────────────────────────────────────

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


# ── Patterns ──────────────────────────────────────────────────────────────────

# Keys that typically hold high-value secrets (should never have weak values)
HIGH_VALUE_KEY_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd|secret|token|api_key|apikey|api_secret|access_key|secret_key|private_key|auth_token|refresh_token|jwt_secret|encryption_key|signing_key)"),
]

# Keywords that indicate a non-secret configuration key (safe to have any value)
NON_SECRET_KEY_PARTS = (
    "env|port|host|url|debug|log|level|name|title|version|mode|dir|path|region|timeout"
    "|max_|min_|enabled|disabled|color|theme|lang|locale|format|type|driver|engine"
    "|prefix|suffix|pool|retry|backoff|interval|count|size|limit|offset|chunk|batch"
    "|worker|thread|proc|replica|shard|partition|slot|queue|topic|channel|exchange"
    "|bucket|database|schema|table|charset|collation|timezone|calendar"
)

NON_SECRET_KEY_PATTERNS = [
    # Matches keys like APP_PORT, DB_HOST, NODE_ENV, LOG_LEVEL, etc.
    re.compile(r"(?i)^(?:[a-z][a-z0-9_]*_)?(" + NON_SECRET_KEY_PARTS + r")$"),
    # Also matches bare names like port, host, env
    re.compile(r"(?i)^(" + NON_SECRET_KEY_PARTS + r")$"),
]

# Weak value patterns (things that look like placeholder/dev/test values)
WEAK_VALUE_PATTERNS = [
    re.compile(r"^changeme$", re.IGNORECASE),
    re.compile(r"^password$", re.IGNORECASE),
    re.compile(r"^secret$", re.IGNORECASE),
    re.compile(r"^test$", re.IGNORECASE),
    re.compile(r"^example$", re.IGNORECASE),
    re.compile(r"^todo$", re.IGNORECASE),
    re.compile(r"^fixme$", re.IGNORECASE),
    re.compile(r"^replace(_?me)?$", re.IGNORECASE),
    re.compile(r"^xxx+$", re.IGNORECASE),
    re.compile(r"^1234(56)?$", re.IGNORECASE),
    re.compile(r"^abc(def)?$", re.IGNORECASE),
    re.compile(r"^default$", re.IGNORECASE),
    re.compile(r"^placeholder$", re.IGNORECASE),
    re.compile(r"^sample$", re.IGNORECASE),
    re.compile(r"^dummy$", re.IGNORECASE),
    re.compile(r"^fake", re.IGNORECASE),
    re.compile(r"^your[_-]?(secret|key|password|token|api)", re.IGNORECASE),
    re.compile(r"^insert[_-]?(your|the|a)?[_-]?(secret|key|password|token|value)", re.IGNORECASE),
    re.compile(r"^\[.*\]$"),  # [placeholder]
    re.compile(r"^<.*>$"),  # <placeholder>
    re.compile(r"^\$\{.*\}$"),  # ${VARIABLE} — unresolved template
]

# Short secret patterns (high-value keys with suspiciously short values)
MIN_SECRET_LENGTH = 12

# Keys that commonly use inline comments that may leak info
INLINE_COMMENT_PATTERN = re.compile(r"#.*$", re.MULTILINE)


# ── Data models ───────────────────────────────────────────────────────────────


@dataclass
class SecurityFinding:
    """A single security issue found in a .env file."""

    severity: str
    rule_id: str
    message: str
    key: str
    value_preview: str = ""
    line_number: int = 0


@dataclass
class SecurityAuditResult:
    """Result of a security audit on one or more .env files."""

    findings: list[SecurityFinding] = field(default_factory=list)
    files_scanned: int = 0
    keys_scanned: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_INFO)

    @property
    def has_critical(self) -> bool:
        return self.critical_count > 0

    @property
    def total_issues(self) -> int:
        return len(self.findings)


# ── Core audit logic ──────────────────────────────────────────────────────────


def _is_high_value_key(key: str) -> bool:
    """Check if a key looks like it holds a high-value secret."""
    return any(p.search(key) for p in HIGH_VALUE_KEY_PATTERNS)


def _is_non_secret_key(key: str) -> bool:
    """Check if a key is clearly a non-secret configuration key."""
    return any(p.search(key) for p in NON_SECRET_KEY_PATTERNS)


def _is_weak_value(value: str) -> bool:
    """Check if a value looks like a placeholder or weak default."""
    if not value:
        return True  # Empty value for a secret key is suspicious
    return any(p.search(value.strip()) for p in WEAK_VALUE_PATTERNS)


def _mask_value(value: str, show: int = 4) -> str:
    """Mask a value for safe display, showing only first few chars."""
    if len(value) <= show:
        return "***"
    return value[:show] + "..." + value[-2:]


def audit_env_content(
    lines: list[str],
    file_path: str = "",
) -> list[SecurityFinding]:
    """Audit the raw lines of a .env file for security issues.

    This scans the raw text (not parsed key-value pairs) so we can
    detect issues like inline comments and whitespace that get lost
    during dotenv parsing.

    Args:
        lines: Raw lines of the .env file.
        file_path: File path for reporting context.

    Returns:
        List of SecurityFinding objects.
    """
    findings: list[SecurityFinding] = []
    seen_keys: dict[str, int] = {}  # key -> first line number

    for line_num, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()

        # Skip empty lines and full-line comments
        if not stripped or stripped.startswith("#"):
            continue

        # Parse KEY=VALUE
        if "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        # ── Rule: Duplicate keys ─────────────────────────────────────────
        if key in seen_keys:
            findings.append(SecurityFinding(
                severity=SEVERITY_WARNING,
                rule_id="ENV-DUP",
                message=f"Duplicate key '{key}' (first defined on line {seen_keys[key]})",
                key=key,
                value_preview=_mask_value(value),
                line_number=line_num,
            ))
        else:
            seen_keys[key] = line_num

        # ── Rule: Inline comments on secret lines ────────────────────────
        # Check if the raw value (after =, before quote stripping) has a trailing comment
        raw_value = stripped.split("=", 1)[1].strip()
        if "#" in raw_value and not raw_value.startswith('"') and not raw_value.startswith("'"):
            # Unquoted value with inline comment — the comment text may leak info
            # or the value may be truncated
            findings.append(SecurityFinding(
                severity=SEVERITY_INFO,
                rule_id="ENV-COMMENT",
                message=f"Inline comment on key '{key}' — may leak context or cause parsing issues",
                key=key,
                value_preview=_mask_value(value),
                line_number=line_num,
            ))

        # Skip non-secret keys for the remaining checks
        if _is_non_secret_key(key) and not _is_high_value_key(key):
            continue

        is_secret_key = _is_high_value_key(key)

        # ── Rule: Weak/placeholder value on a secret key ─────────────────
        if is_secret_key and _is_weak_value(value):
            findings.append(SecurityFinding(
                severity=SEVERITY_CRITICAL,
                rule_id="ENV-WEAK",
                message=f"Secret key '{key}' has a weak or placeholder value",
                key=key,
                value_preview=_mask_value(value) if value else "(empty)",
                line_number=line_num,
            ))
            continue  # No need to check length if value is weak

        # ── Rule: Short secret value ─────────────────────────────────────
        if is_secret_key and 0 < len(value) < MIN_SECRET_LENGTH:
            findings.append(SecurityFinding(
                severity=SEVERITY_WARNING,
                rule_id="ENV-SHORT",
                message=f"Secret key '{key}' has a short value ({len(value)} chars, recommend ≥{MIN_SECRET_LENGTH})",
                key=key,
                value_preview=_mask_value(value),
                line_number=line_num,
            ))

        # ── Rule: Unquoted value with special characters ─────────────────
        if is_secret_key and any(c in value for c in " #'$\\\""):
            raw_val = stripped.split("=", 1)[1].strip()
            if not (raw_val.startswith('"') or raw_val.startswith("'")):
                findings.append(SecurityFinding(
                    severity=SEVERITY_WARNING,
                    rule_id="ENV-UNQUOTED",
                    message=f"Secret key '{key}' has unquoted value with special characters — may be parsed incorrectly",
                    key=key,
                    value_preview=_mask_value(value),
                    line_number=line_num,
                ))

    return findings


def audit_env_file(file_path: str | Path) -> tuple[list[SecurityFinding], int]:
    """Audit a single .env file for security issues.

    Args:
        file_path: Path to the .env file.

    Returns:
        Tuple of (findings, key_count).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Env file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    findings = audit_env_content(lines, str(file_path))

    # Count keys
    key_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key_count += 1

    return findings, key_count


def run_security_audit(
    env_files: list[str | Path],
    *,
    strict: bool = False,
) -> SecurityAuditResult:
    """Run a full security audit across one or more .env files.

    Args:
        env_files: List of .env file paths to audit.
        strict: If True, treat warnings as critical (useful for CI).

    Returns:
        SecurityAuditResult with all findings.
    """
    result = SecurityAuditResult()
    all_keys: set[str] = set()

    for file_path in env_files:
        file_path = Path(file_path)
        if not file_path.exists():
            continue

        result.files_scanned += 1
        findings, key_count = audit_env_file(file_path)
        result.keys_scanned += key_count

        # Cross-file: track keys for duplicate detection across files
        content = file_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                all_keys.add(key)

        if strict:
            for f in findings:
                if f.severity == SEVERITY_WARNING:
                    f.severity = SEVERITY_CRITICAL

        result.findings.extend(findings)

    # ── Rule: File permission check (Unix only) ──────────────────────────
    is_windows = platform.system() == "Windows"

    for file_path in env_files:
        file_path = Path(file_path)
        if not file_path.exists():
            continue
        if is_windows:
            continue  # Permission bits are meaningless on Windows
        try:
            mode = file_path.stat().st_mode
            # Check if group or others have read permission
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                result.findings.append(SecurityFinding(
                    severity=SEVERITY_WARNING,
                    rule_id="ENV-PERMS",
                    message=f"File is readable by group/others (mode: {oct(mode & 0o777)}) — restrict with chmod 600",
                    key="(file)",
                    value_preview=str(file_path),
                ))
        except OSError:
            pass  # Windows or other platforms may not support full stat

    # ── Rule: .env file not in .gitignore ────────────────────────────────
    for file_path in env_files:
        file_path = Path(file_path)
        if not file_path.exists():
            continue
        # Check if there's a .gitignore in parent dirs that covers this file
        _check_gitignore(file_path, result)

    return result


def _check_gitignore(env_path: Path, result: SecurityAuditResult) -> None:
    """Check if the .env file is covered by a .gitignore entry."""
    # Walk up from the env file directory looking for a .git directory first
    # If not inside a git repo, skip the gitignore check (no risk of committing)
    current = env_path.parent.resolve()
    env_name = env_path.name
    in_git_repo = False

    for _ in range(10):  # Max 10 directories up
        if (current / ".git").exists():
            in_git_repo = True
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    if not in_git_repo:
        return  # Not in a git repo — gitignore check is N/A

    # Now walk up looking for .gitignore
    current = env_path.parent.resolve()
    for _ in range(10):  # Max 10 directories up
        gitignore = current / ".gitignore"
        if gitignore.exists():
            try:
                content = gitignore.read_text(encoding="utf-8")
                patterns = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
                # Check if any pattern matches
                for pattern in patterns:
                    # Simple matching — .env, *.env, .env.*, etc.
                    if pattern == env_name or pattern == f".{env_name.lstrip('.')}":
                        return  # Covered
                    if pattern.startswith("*") and env_name.endswith(pattern[1:]):
                        return  # Wildcard covered
                if (pattern == ".env*" or pattern == "*.env" or pattern == ".env.*") and (
                    env_name.startswith(".env") or env_name.endswith(".env")
                ):
                    return
            except OSError:
                pass
            break  # Only check the closest .gitignore

        parent = current.parent
        if parent == current:
            break
        current = parent

    # If we got here, the file isn't covered by .gitignore
    result.findings.append(SecurityFinding(
        severity=SEVERITY_CRITICAL,
        rule_id="ENV-GITIGNORE",
        message=f"'{env_name}' is not in .gitignore — risk of committing secrets to version control",
        key="(file)",
        value_preview=str(env_path),
    ))


def format_security_report(result: SecurityAuditResult, file_label: str = "") -> str:
    """Format a SecurityAuditResult as a human-readable report.

    Args:
        result: The audit result to format.
        file_label: Optional label for the file(s) scanned.

    Returns:
        A formatted string report.
    """
    lines: list[str] = []

    if file_label:
        lines.append(f"Security Audit: {file_label}")
    lines.append(f"Files scanned: {result.files_scanned} | Keys scanned: {result.keys_scanned}")

    if not result.findings:
        lines.append("\n  No security issues found.")
        return "\n".join(lines)

    # Group by severity
    criticals = [f for f in result.findings if f.severity == SEVERITY_CRITICAL]
    warnings = [f for f in result.findings if f.severity == SEVERITY_WARNING]
    infos = [f for f in result.findings if f.severity == SEVERITY_INFO]

    lines.append(f"\n  Issues: {result.critical_count} critical, {result.warning_count} warning, {result.info_count} info")

    if criticals:
        lines.append(f"\n  CRITICAL ({len(criticals)}):")
        for f in criticals:
            loc = f" (line {f.line_number})" if f.line_number else ""
            lines.append(f"    [{f.rule_id}] {f.message}{loc}")
            if f.value_preview:
                lines.append(f"           value: {f.value_preview}")

    if warnings:
        lines.append(f"\n  WARNING ({len(warnings)}):")
        for f in warnings:
            loc = f" (line {f.line_number})" if f.line_number else ""
            lines.append(f"    [{f.rule_id}] {f.message}{loc}")
            if f.value_preview:
                lines.append(f"           value: {f.value_preview}")

    if infos:
        lines.append(f"\n  INFO ({len(infos)}):")
        for f in infos:
            loc = f" (line {f.line_number})" if f.line_number else ""
            lines.append(f"    [{f.rule_id}] {f.message}{loc}")

    return "\n".join(lines)
