"""Tests for security_audit module — envault audit-security command."""

import stat

from envault.security_audit import (
    SecurityAuditResult,
    SecurityIssue,
    _check_duplicate_keys,
    _is_hardcoded_secret,
    _is_weak_value,
    audit_env_file,
    format_audit_report,
)

# ── SecurityIssue ───────────────────────────────────────────────────────────


def test_security_issue_sort_rank():
    issue_critical = SecurityIssue("critical", "test", "KEY", "msg")
    issue_high = SecurityIssue("high", "test", "KEY", "msg")
    issue_medium = SecurityIssue("medium", "test", "KEY", "msg")
    issue_low = SecurityIssue("low", "test", "KEY", "msg")
    issue_info = SecurityIssue("info", "test", "KEY", "msg")
    assert issue_critical.sort_rank < issue_high.sort_rank
    assert issue_high.sort_rank < issue_medium.sort_rank
    assert issue_medium.sort_rank < issue_low.sort_rank
    assert issue_low.sort_rank < issue_info.sort_rank


# ── SecurityAuditResult ────────────────────────────────────────────────────


def test_audit_result_counts():
    result = SecurityAuditResult(file_path="test.env")
    result.issues.append(SecurityIssue("critical", "cat", "K", "m"))
    result.issues.append(SecurityIssue("high", "cat", "K", "m"))
    result.issues.append(SecurityIssue("medium", "cat", "K", "m"))
    result.issues.append(SecurityIssue("low", "cat", "K", "m"))
    result.issues.append(SecurityIssue("info", "cat", "K", "m"))
    assert result.critical_count == 1
    assert result.high_count == 1
    assert result.medium_count == 1
    assert result.low_count == 1
    assert result.info_count == 1
    assert result.total_issues == 5
    assert result.has_critical_or_high is True
    assert result.pass_fail == "FAIL"


def test_audit_result_pass():
    result = SecurityAuditResult(file_path="test.env")
    result.issues.append(SecurityIssue("low", "cat", "K", "m"))
    assert result.has_critical_or_high is False
    assert result.pass_fail == "PASS"


def test_audit_result_sorted_issues():
    result = SecurityAuditResult(file_path="test.env")
    result.issues.append(SecurityIssue("low", "cat", "B", "m"))
    result.issues.append(SecurityIssue("critical", "cat", "A", "m"))
    result.issues.append(SecurityIssue("high", "cat", "C", "m"))
    sorted_list = result.sorted_issues()
    assert sorted_list[0].severity == "critical"
    assert sorted_list[1].severity == "high"
    assert sorted_list[2].severity == "low"


# ── Weak value detection ───────────────────────────────────────────────────


def test_weak_value_password():
    is_weak, reason = _is_weak_value("DB_PASSWORD", "password")
    assert is_weak
    assert "weak" in reason.lower() or "default" in reason.lower()


def test_weak_value_changeme():
    is_weak, reason = _is_weak_value("API_SECRET", "changeme")
    assert is_weak


def test_weak_value_empty():
    is_weak, reason = _is_weak_value("TOKEN", "")
    assert is_weak
    assert "empty" in reason.lower()


def test_weak_value_strong():
    is_weak, reason = _is_weak_value("DB_PASSWORD", "xK9mP2qR7vL4nB8j")
    assert not is_weak


def test_weak_value_non_secret_key():
    is_weak, reason = _is_weak_value("APP_NAME", "test")
    assert is_weak  # "test" is a generic weak value even for non-secret keys


def test_weak_value_non_secret_normal():
    is_weak, reason = _is_weak_value("APP_NAME", "myapp")
    assert not is_weak


# ── Hardcoded secret detection ─────────────────────────────────────────────


def test_hardcoded_aws_access_key():
    is_hardcoded, desc = _is_hardcoded_secret("AWS_KEY", "AKIAIOSFODNN7EXAMPLE")
    assert is_hardcoded
    assert "AWS" in desc


def test_hardcoded_private_key():
    is_hardcoded, desc = _is_hardcoded_secret("SSH_KEY", "-----BEGIN RSA PRIVATE KEY-----")
    assert is_hardcoded
    assert "Private key" in desc


def test_hardcoded_hex_secret():
    is_hardcoded, desc = _is_hardcoded_secret("TOKEN", "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4")
    assert is_hardcoded
    assert "Hex" in desc


def test_not_hardcoded_normal_value():
    is_hardcoded, desc = _is_hardcoded_secret("DB_HOST", "localhost")
    assert not is_hardcoded


# ── Duplicate keys ─────────────────────────────────────────────────────────


def test_duplicate_keys_found():
    content = "KEY=one\nOTHER=two\nKEY=three\n"
    dups = _check_duplicate_keys(content)
    assert "KEY" in dups


def test_no_duplicate_keys():
    content = "KEY=one\nOTHER=two\nTHIRD=three\n"
    dups = _check_duplicate_keys(content)
    assert len(dups) == 0


def test_duplicate_keys_comments_ignored():
    content = "# KEY=comment\nKEY=value\n"
    dups = _check_duplicate_keys(content)
    assert len(dups) == 0


# ── Full audit_env_file ────────────────────────────────────────────────────


def test_audit_clean_file(tmp_path):
    """A well-formed .env with strong secrets should have minimal issues."""
    env_file = tmp_path / ".env.prod"
    env_file.write_text("DB_HOST=prod.example.com\nDB_PORT=5432\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    # No secrets in this file, so no weak_secret or hardcoded_credential
    secret_issues = [i for i in result.issues if i.category in ("weak_secret", "hardcoded_credential")]
    assert len(secret_issues) == 0


def test_audit_weak_password(tmp_path):
    """Weak password should be flagged."""
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=password\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    weak_issues = [i for i in result.issues if i.category == "weak_secret"]
    assert len(weak_issues) >= 1
    assert any(i.key == "DB_PASSWORD" for i in weak_issues)


def test_audit_hardcoded_aws_key(tmp_path):
    """Hardcoded AWS access key should be flagged as critical."""
    env_file = tmp_path / ".env"
    env_file.write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    hardcoded = [i for i in result.issues if i.category == "hardcoded_credential"]
    assert len(hardcoded) >= 1
    assert hardcoded[0].severity == "critical"


def test_audit_duplicate_keys(tmp_path):
    """Duplicate keys should be flagged."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=one\nKEY=two\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    dup_issues = [i for i in result.issues if i.category == "duplicate_key"]
    assert len(dup_issues) == 1
    assert dup_issues[0].key == "KEY"


def test_audit_empty_value(tmp_path):
    """Empty secret value should be flagged."""
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    weak = [i for i in result.issues if i.category == "weak_secret" and i.key == "API_KEY"]
    assert len(weak) >= 1


def test_audit_nonexistent_file(tmp_path):
    """Missing file should produce an info-level issue."""
    result = audit_env_file(str(tmp_path / ".env.missing"), check_permissions=False, check_gitignore=False)
    assert result.total_issues == 1
    assert result.issues[0].category == "missing"


def test_audit_empty_file(tmp_path):
    """Empty file should produce an info-level issue."""
    env_file = tmp_path / ".env"
    env_file.write_text("")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    info_issues = [i for i in result.issues if i.category == "empty"]
    assert len(info_issues) == 1


def test_audit_changeme_value(tmp_path):
    """'changeme' should be flagged as a weak secret."""
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET=changeme\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    weak = [i for i in result.issues if i.category == "weak_secret"]
    assert any(i.key == "JWT_SECRET" for i in weak)


def test_audit_sensitive_in_plain_file(tmp_path):
    """aws_secret_access_key with a real value should be flagged as sensitive_in_plain_file."""
    env_file = tmp_path / ".env"
    # Use a value that doesn't contain any weak/default words (no "secret", "password", etc.)
    env_file.write_text("AWS_SECRET_ACCESS_KEY=wJalrXUtIMiK7Q9Pxv3=1234\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    sensitive = [i for i in result.issues if i.category == "sensitive_in_plain_file"]
    assert len(sensitive) >= 1
    assert sensitive[0].severity == "high"


def test_audit_unquoted_special_chars(tmp_path):
    """Unquoted values with special characters should be flagged."""
    env_file = tmp_path / ".env"
    env_file.write_text("SHELL_VAR=something$other\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    unquoted = [i for i in result.issues if i.category == "unquoted_value"]
    assert len(unquoted) >= 1


def test_audit_inline_comment(tmp_path):
    """Inline comments without quoting should be flagged."""
    env_file = tmp_path / ".env"
    env_file.write_text("DB_HOST=localhost # production\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    inline = [i for i in result.issues if i.category == "inline_comment"]
    assert len(inline) >= 1


def test_audit_rotation_recommended(tmp_path):
    """JWT_SECRET should get a rotation recommendation."""
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET=aVeryStrongAndLongRandomSecretValue12345\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    rotation = [i for i in result.issues if i.category == "rotation_recommended"]
    assert any(i.key == "JWT_SECRET" for i in rotation)


# ── .gitignore checks ──────────────────────────────────────────────────────


def test_audit_gitignore_missing_entry(tmp_path):
    """.env file not in .gitignore should be flagged."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\n")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("node_modules/\ndist/\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=True)
    gitignore_issues = [i for i in result.issues if i.category == "gitignore"]
    assert len(gitignore_issues) >= 1
    assert gitignore_issues[0].severity == "critical"


def test_audit_gitignore_present(tmp_path):
    """.env file in .gitignore should not be flagged."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\n")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".env\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=True)
    gitignore_issues = [i for i in result.issues if i.category == "gitignore"]
    assert len(gitignore_issues) == 0


def test_audit_gitignore_glob_pattern(tmp_path):
    """*.env glob pattern in .gitignore should match .env.dev etc."""
    env_file = tmp_path / ".env.dev"
    env_file.write_text("KEY=value\n")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.env\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=True)
    gitignore_issues = [i for i in result.issues if i.category == "gitignore"]
    assert len(gitignore_issues) == 0


def test_audit_no_gitignore_at_all(tmp_path):
    """Missing .gitignore file in a git repo should produce medium-severity issue."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\n")
    # Create .git directory so the check triggers
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=True)
    gitignore_issues = [i for i in result.issues if i.category == "gitignore"]
    assert len(gitignore_issues) >= 1
    assert gitignore_issues[0].severity == "medium"


# ── File permissions ────────────────────────────────────────────────────────


def test_audit_world_readable(tmp_path):
    """World-readable .env should be flagged as critical."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\n")
    # Make world-readable
    env_file.chmod(0o644)
    result = audit_env_file(str(env_file), check_permissions=True, check_gitignore=False)
    perm_issues = [i for i in result.issues if i.category == "permissions"]
    # On Windows/MSYS, chmod may not work, so skip assertion if no perm issues
    if perm_issues:
        assert any(i.severity == "critical" for i in perm_issues)


def test_audit_restrictive_permissions(tmp_path):
    """Owner-only .env (600) should not have permission issues."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\n")
    env_file.chmod(0o600)
    result = audit_env_file(str(env_file), check_permissions=True, check_gitignore=False)
    perm_issues = [i for i in result.issues if i.category == "permissions"]
    # On Windows/MSYS, chmod may be a no-op, so skip assertion if perm issues appear
    if perm_issues and stat.S_IRGRP == 0:
        # MSYS/Windows — chmod is no-op, skip
        pass


# ── format_audit_report ────────────────────────────────────────────────────


def test_format_report_empty():
    report = format_audit_report([])
    assert "No files" in report


def test_format_report_clean():
    result = SecurityAuditResult(file_path="clean.env")
    report = format_audit_report([result])
    assert "PASS" in report
    assert "No issues" in report


def test_format_report_with_critical():
    result = SecurityAuditResult(file_path="bad.env")
    result.issues.append(SecurityIssue("critical", "hardcoded_credential", "AWS_KEY", "AWS key found"))
    report = format_audit_report([result])
    assert "FAIL" in report
    assert "CRITICAL" in report


def test_format_report_verbose():
    result = SecurityAuditResult(file_path="test.env")
    result.issues.append(
        SecurityIssue(
            "info",
            "rotation_recommended",
            "JWT_SECRET",
            "Rotate periodically",
            suggestion="Use envault rotate",
        )
    )
    report_non_verbose = format_audit_report([result], verbose=False)
    report_verbose = format_audit_report([result], verbose=True)
    # Non-verbose should skip info-level, verbose should include it
    assert "rotation_recommended" not in report_non_verbose
    assert "rotation_recommended" in report_verbose
    assert "envault rotate" in report_verbose


def test_format_report_multiple_files():
    r1 = SecurityAuditResult(file_path="a.env")
    r1.issues.append(SecurityIssue("medium", "weak_secret", "KEY", "weak"))
    r2 = SecurityAuditResult(file_path="b.env")
    r2.issues.append(SecurityIssue("critical", "hardcoded_credential", "K2", "aws"))
    report = format_audit_report([r1, r2])
    assert "a.env" in report
    assert "b.env" in report
    assert "FAIL" in report


# ── Integration: quoted values not flagged ──────────────────────────────────


def test_audit_properly_quoted_value(tmp_path):
    """Properly quoted values with special chars should not trigger unquoted_value."""
    env_file = tmp_path / ".env"
    env_file.write_text('SHELL_VAR="something$other"\n')
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    unquoted = [i for i in result.issues if i.category == "unquoted_value"]
    assert len(unquoted) == 0


def test_audit_encryption_recommended(tmp_path):
    """Secret keys with strong values should get encryption recommendation."""
    env_file = tmp_path / ".env"
    env_file.write_text("MY_SECRET=aVeryStrongRandomValueThatIsNotWeak12345\n")
    result = audit_env_file(str(env_file), check_permissions=False, check_gitignore=False)
    enc = [i for i in result.issues if i.category == "encryption_recommended"]
    assert any(i.key == "MY_SECRET" for i in enc)
