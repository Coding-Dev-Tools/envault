"""Security audit for .env files — checks for common security issues."""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

# ── Issue types ──────────────────────────────────────────────────────────────


@dataclass
class SecurityIssue:
    """A single security finding in a .env file."""

    severity: str  # "critical" | "high" | "medium" | "low" | "info"
    category: str  # e.g. "weak_secret", "hardcoded_credential", "permissions"
    key: str  # env var name (or "" for file-level issues)
    message: str
    suggestion: str = ""

    @property
    def sort_rank(self) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(self.severity, 5)


@dataclass
class SecurityAuditResult:
    """Aggregated result of a security audit."""

    file_path: str
    issues: list[SecurityIssue] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "high")

    @property
    def medium_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "medium")

    @property
    def low_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "low")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")

    @property
    def total_issues(self) -> int:
        return len(self.issues)

    @property
    def has_critical_or_high(self) -> bool:
        return self.critical_count > 0 or self.high_count > 0

    @property
    def pass_fail(self) -> str:
        return "FAIL" if self.has_critical_or_high else "PASS"

    def sorted_issues(self) -> list[SecurityIssue]:
        return sorted(self.issues, key=lambda i: (i.sort_rank, i.key))


# ── Checks ──────────────────────────────────────────────────────────────────

# Known weak/test values that should never appear in real secrets
WEAK_VALUES: dict[str, list[str]] = {
    "generic": [
        "password",
        "secret",
        "changeme",
        "123456",
        "admin",
        "test",
        "example",
        "todo",
        "fixme",
        "xxx",
    ],
    "database": ["root", "postgres", "sa", "dbadmin"],
    "api_key": [
        "sk_test_",
        "pk_test_",
        "your_api_key",
        "xxx",
        "key_here",
        "api_key_here",
    ],
}

# Keys that typically hold high-value secrets and must not be weak
SECRET_KEY_PATTERNS = [
    (re.compile(r"(password|passwd|pass)", re.I), "database"),
    (re.compile(r"(api_key|apikey|api_secret|apisecret)", re.I), "api_key"),
    (re.compile(r"(secret|token|auth|credential)", re.I), "generic"),
    (re.compile(r"(jwt|signing_key|encryption_key)", re.I), "generic"),
    (re.compile(r"(aws_|gcp_|azure_)", re.I), "api_key"),
    (re.compile(r"(private_key|ssh_key|rsa_)", re.I), "generic"),
]

# Keys that should never be committed
NEVER_COMMIT_KEYS = re.compile(
    r"(aws_secret_access_key|private_key|ssh_private|gcp_service_account_key|azure_client_secret)",
    re.I,
)

# Patterns for sensitive values that look hardcoded
HARDCODED_VALUE_PATTERNS = [
    # AWS access keys
    (re.compile(r"^AKIA[0-9A-Z]{16}$"), "AWS Access Key ID detected"),
    # AWS secret keys (40-char base64-ish with mixed case and /+=)
    (re.compile(r"^[A-Za-z0-9/+=]{40}$"), "Possible AWS Secret Access Key"),
    # Private key markers
    (re.compile(r"-----BEGIN.*PRIVATE KEY-----"), "Private key material detected"),
    # Generic long hex strings that look like real secrets
    (re.compile(r"^[0-9a-f]{32,}$"), "Hex-encoded secret detected"),
    # Long base64 with slashes/pluses (very likely a real credential)
    (re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$"), "Base64-encoded secret detected"),
]

# Common keys that should use encryption at rest
ENCRYPTION_RECOMMENDED_KEYS = re.compile(
    r"(password|secret|token|api_key|private_key|credential)",
    re.I,
)

# Keys that should be rotated periodically
ROTATION_RECOMMENDED_KEYS = re.compile(
    r"(jwt_secret|api_key|api_secret|database_password|db_password|session_secret|signing_key)",
    re.I,
)


def _is_weak_value(key: str, value: str) -> tuple[bool, str]:
    """Check if a value looks like a weak/placeholder secret."""
    if not value or not value.strip():
        return True, "Empty value"

    val_lower = value.strip().lower()

    # Build a word-boundary check: match weak values as whole words
    # to avoid false positives like "my-secret-key" matching "secret"
    def _is_weak_match(weak_val: str, text: str) -> bool:
        # For short/generic words, require word boundary match
        # For longer patterns (e.g. "sk_test_"), use substring match
        if len(weak_val) <= 6:
            return bool(re.search(r"\b" + re.escape(weak_val) + r"\b", text))
        else:
            return weak_val in text

    # Check key-type-specific weak values
    for pattern, category in SECRET_KEY_PATTERNS:
        if pattern.search(key):
            # Check category-specific weak values first, then fall back to generic
            for weak_list_source in [category, "generic"]:
                weak_list = WEAK_VALUES.get(weak_list_source, [])
                for weak in weak_list:
                    if _is_weak_match(weak, val_lower):
                        return True, f"Contains weak/default value '{weak}'"
            # Matched a secret-key pattern but no weak value found
            return False, ""

    # For non-secret keys, only check generic weak values
    for weak in WEAK_VALUES["generic"]:
        if val_lower == weak:
            return True, f"Value is the weak/default '{weak}'"

    return False, ""


def _is_hardcoded_secret(key: str, value: str) -> tuple[bool, str]:
    """Check if a value looks like a real hardcoded secret that shouldn't be in .env."""
    for pattern, description in HARDCODED_VALUE_PATTERNS:
        if pattern.search(value):
            # For base64 patterns, require some non-alphanumeric chars to avoid
            # false positives on long alphanumeric strings (e.g. "aVeryStrongRandomValue12345")
            if description in (
                "Base64-encoded secret detected",
                "Possible AWS Secret Access Key",
            ) and not re.search(r"[/+=]", value):
                continue
            return True, description
    return False, ""


def _check_duplicate_keys(content: str) -> list[str]:
    """Find keys that appear more than once in the file."""
    keys: list[str] = []
    seen: dict[str, int] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match:
            k = match.group(1)
            seen[k] = seen.get(k, 0) + 1
            if seen[k] > 1:
                keys.append(k)
    return keys


def _check_file_permissions(file_path: Path) -> list[SecurityIssue]:
    """Check if the .env file has overly permissive filesystem permissions."""
    issues: list[SecurityIssue] = []
    try:
        mode = file_path.stat().st_mode
        # Check if group or others can read
        if mode & stat.S_IRGRP:
            issues.append(
                SecurityIssue(
                    severity="high",
                    category="permissions",
                    key="",
                    message=f"File is group-readable (mode={oct(mode & 0o777)})",
                    suggestion="Run: chmod 600 <file> to restrict to owner only",
                )
            )
        if mode & stat.S_IROTH:
            issues.append(
                SecurityIssue(
                    severity="critical",
                    category="permissions",
                    key="",
                    message=f"File is world-readable (mode={oct(mode & 0o777)})",
                    suggestion="Run: chmod 600 <file> to restrict to owner only",
                )
            )
        if mode & stat.S_IWGRP:
            issues.append(
                SecurityIssue(
                    severity="medium",
                    category="permissions",
                    key="",
                    message=f"File is group-writable (mode={oct(mode & 0o777)})",
                    suggestion="Run: chmod 600 <file> to restrict to owner only",
                )
            )
    except OSError:
        pass  # Permission checks not available on some platforms / file systems
    return issues


def _check_gitignore(file_path: Path) -> list[SecurityIssue]:
    """Check if the .env file is listed in .gitignore."""
    issues: list[SecurityIssue] = []

    # Walk up to find .git and .gitignore, but stop at repo root (.git directory)
    current = file_path.parent.resolve()
    gitignore_found = False
    is_ignored = False
    repo_root_found = False

    for _ in range(20):  # Limit traversal depth
        gitignore = current / ".gitignore"
        git_dir = current / ".git"

        # Track whether we're inside a git repo
        if git_dir.is_dir():
            repo_root_found = True

        if gitignore.exists():
            gitignore_found = True
            try:
                content = gitignore.read_text()
                filename = file_path.name
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Exact name match
                    if line == filename or line == f"/{filename}":
                        is_ignored = True
                        break
                    # *.ext glob pattern (e.g. *.env matches .env, .env.dev, .env.prod)
                    if line.startswith("*."):
                        ext = line[2:]  # e.g. "env"
                        if filename == f".{ext}" or filename.startswith(f".{ext}.") or filename.startswith(f".{ext}-"):
                            is_ignored = True
                            break
                        # Also handle non-dot files: *.key matches server.key
                        if filename.endswith(f".{ext}"):
                            is_ignored = True
                            break
                    # prefix* glob pattern (e.g. .env* matches .env.dev)
                    if line.endswith("*"):
                        prefix = line.rstrip("*")
                        if filename.startswith(prefix):
                            is_ignored = True
                            break
                if is_ignored:
                    break
            except OSError:
                pass

        # Stop walking at the repo root — don't go above .git directory
        if repo_root_found:
            break

        parent = current.parent
        if parent == current:
            break
        current = parent

    if gitignore_found and not is_ignored:
        issues.append(
            SecurityIssue(
                severity="critical",
                category="gitignore",
                key="",
                message=f"'{file_path.name}' is not in .gitignore — secrets may be committed to version control",
                suggestion=f"Add '{file_path.name}' to .gitignore",
            )
        )

    # Don't flag missing gitignore if we already flagged a specific file issue
    if not gitignore_found and not issues and repo_root_found:
        issues.append(
            SecurityIssue(
                severity="medium",
                category="gitignore",
                key="",
                message="No .gitignore found — .env files may be committed to version control",
                suggestion="Add a .gitignore and include .env files",
            )
        )

    return issues


def audit_env_file(
    file_path: str | Path,
    *,
    check_permissions: bool = True,
    check_gitignore: bool = True,
) -> SecurityAuditResult:
    """Run a security audit on a .env file.

    Args:
        file_path: Path to the .env file to audit.
        check_permissions: Whether to check filesystem permissions.
        check_gitignore: Whether to check .gitignore coverage.

    Returns:
        SecurityAuditResult with all found issues.
    """
    file_path = Path(file_path)
    result = SecurityAuditResult(file_path=str(file_path))

    if not file_path.exists():
        result.issues.append(
            SecurityIssue(
                severity="info",
                category="missing",
                key="",
                message=f"File '{file_path}' does not exist",
            )
        )
        return result

    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    # ── File-level checks ─────────────────────────────────────────────────

    # File permissions
    if check_permissions:
        result.issues.extend(_check_file_permissions(file_path))

    # .gitignore coverage
    if check_gitignore:
        result.issues.extend(_check_gitignore(file_path))

    # Empty file
    if not content.strip():
        result.issues.append(
            SecurityIssue(
                severity="info",
                category="empty",
                key="",
                message="File is empty",
            )
        )
        return result

    # Duplicate keys
    duplicates = _check_duplicate_keys(content)
    for dup_key in duplicates:
        result.issues.append(
            SecurityIssue(
                severity="medium",
                category="duplicate_key",
                key=dup_key,
                message=f"Duplicate key '{dup_key}' — last assignment wins, earlier values are masked",
                suggestion="Remove the duplicate assignment",
            )
        )

    # ── Per-key checks ────────────────────────────────────────────────────

    for _line_num, line in enumerate(lines, 1):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line_stripped)
        if not match:
            continue

        key, raw_value = match.group(1), match.group(2)

        # Unquote value
        value = raw_value.strip()
        if len(value) >= 2 and (
            (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]

        # 1. Weak/placeholder secrets
        is_weak, weak_reason = _is_weak_value(key, value)
        if is_weak:
            result.issues.append(
                SecurityIssue(
                    severity="high" if NEVER_COMMIT_KEYS.search(key) else "medium",
                    category="weak_secret",
                    key=key,
                    message=f"Weak/placeholder value for '{key}': {weak_reason}",
                    suggestion="Replace with a strong generated secret (use 'envault rotate')",
                )
            )

        # 2. Hardcoded secrets that look real (and thus dangerous in .env)
        is_hardcoded, hardcoded_desc = _is_hardcoded_secret(key, value)
        if is_hardcoded:
            result.issues.append(
                SecurityIssue(
                    severity="critical",
                    category="hardcoded_credential",
                    key=key,
                    message=f"'{key}': {hardcoded_desc}",
                    suggestion="Move to a secret store (e.g. envault store set) and reference via store integration",
                )
            )

        # 3. Never-commit keys found in plain .env
        if NEVER_COMMIT_KEYS.search(key) and value and not _is_weak_value(key, value)[0]:
            # Only flag if not already flagged at higher severity
            already_flagged = any(i.key == key and i.category == "hardcoded_credential" for i in result.issues)
            if not already_flagged:
                result.issues.append(
                    SecurityIssue(
                        severity="high",
                        category="sensitive_in_plain_file",
                        key=key,
                        message=f"'{key}' is a high-sensitivity key stored in plain .env file",
                        suggestion="Encrypt with 'envault encrypt' or move to a secret store",
                    )
                )

        # 4. Encryption recommended
        if ENCRYPTION_RECOMMENDED_KEYS.search(key) and value and not _is_weak_value(key, value)[0]:
            # Only flag if not already flagged as hardcoded or sensitive
            already_flagged = any(
                i.key == key and i.category in ("hardcoded_credential", "sensitive_in_plain_file")
                for i in result.issues
            )
            if not already_flagged:
                result.issues.append(
                    SecurityIssue(
                        severity="low",
                        category="encryption_recommended",
                        key=key,
                        message=f"'{key}' stores a secret — consider encrypting at rest",
                        suggestion="Use 'envault encrypt' or a secret store integration",
                    )
                )

        # 5. Rotation recommended
        if ROTATION_RECOMMENDED_KEYS.search(key):
            result.issues.append(
                SecurityIssue(
                    severity="info",
                    category="rotation_recommended",
                    key=key,
                    message=f"'{key}' should be rotated periodically",
                    suggestion="Use 'envault rotate' to generate a new value",
                )
            )

        # 6. Unquoted values with special characters (shell injection risk)
        if raw_value.strip() and not raw_value.strip().startswith(('"', "'")) and any(c in value for c in " $`\\!#"):
            result.issues.append(
                SecurityIssue(
                    severity="low",
                    category="unquoted_value",
                    key=key,
                    message=f"'{key}' has unquoted value containing special characters — may cause shell expansion issues",
                    suggestion='Quote the value: {key}="{value}"',
                )
            )

        # 7. Inline comments without quoting (dotenv misparse risk)
        if not raw_value.strip().startswith(('"', "'")) and " #" in raw_value:
            result.issues.append(
                SecurityIssue(
                    severity="low",
                    category="inline_comment",
                    key=key,
                    message=f"'{key}' has an inline comment — dotenv parsers may include '#...' in the value",
                    suggestion="Quote the value or put comments on separate lines",
                )
            )

    return result


def format_audit_report(results: list[SecurityAuditResult], *, verbose: bool = False) -> str:
    """Format security audit results into a human-readable report.

    Args:
        results: One or more audit results.
        verbose: Include info-level findings.

    Returns:
        Formatted report string.
    """
    lines: list[str] = []
    total_issues = 0
    total_critical = 0
    total_high = 0
    overall_pass = True

    for result in results:
        lines.append("")
        lines.append(f"  Security Audit: {result.file_path}")

        if not result.issues:
            lines.append("  ✓ No issues found")
            continue

        issues_to_show = result.sorted_issues()
        if not verbose:
            issues_to_show = [i for i in issues_to_show if i.severity != "info"]

        for issue in issues_to_show:
            severity_icon = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🔵",
                "info": "⚪",
            }.get(issue.severity, "  ")

            key_part = f"[{issue.key}] " if issue.key else ""
            lines.append(f"  {severity_icon} {issue.severity.upper():8} {issue.category:24} {key_part}{issue.message}")
            if issue.suggestion and verbose:
                lines.append(f"           → {issue.suggestion}")

        total_issues += result.total_issues
        total_critical += result.critical_count
        total_high += result.high_count
        if result.has_critical_or_high:
            overall_pass = False

    # Summary
    lines.append("")
    if not results:
        lines.append("  No files audited.")
    else:
        status = "PASS ✓" if overall_pass else "FAIL ✗"
        lines.append("  ── Summary ──")
        lines.append(f"  {status}  {len(results)} file(s)  {total_issues} issue(s)")
        if total_critical or total_high:
            lines.append(
                f"  🔴 Critical: {total_critical}  🟠 High: {total_high}  🟡 Medium: {sum(r.medium_count for r in results)}  🔵 Low: {sum(r.low_count for r in results)}"
            )

    return "\n".join(lines)
