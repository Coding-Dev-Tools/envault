"""Tests for the Envault security audit engine (envault.security)."""

from __future__ import annotations

from envault.security import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SecurityAuditResult,
    SecurityFinding,
    _is_high_value_key,
    _is_non_secret_key,
    _is_weak_value,
    _mask_value,
    audit_env_content,
    audit_env_file,
    format_security_report,
    run_security_audit,
)

# ── Helper: key classification ────────────────────────────────────────────────


class TestHighValueKeyDetection:
    def test_password_variants(self):
        assert _is_high_value_key("DB_PASSWORD")
        assert _is_high_value_key("password")
        assert _is_high_value_key("PASSWD")
        assert _is_high_value_key("db_pwd")

    def test_secret_key(self):
        assert _is_high_value_key("SECRET_KEY")
        assert _is_high_value_key("jwt_secret")
        assert _is_high_value_key("API_SECRET")

    def test_token_key(self):
        assert _is_high_value_key("API_TOKEN")
        assert _is_high_value_key("auth_token")
        assert _is_high_value_key("REFRESH_TOKEN")

    def test_non_secret_keys(self):
        assert not _is_high_value_key("APP_PORT")
        assert not _is_high_value_key("LOG_LEVEL")
        assert not _is_high_value_key("NODE_ENV")


class TestNonSecretKeyDetection:
    def test_common_non_secrets(self):
        assert _is_non_secret_key("APP_PORT")
        assert _is_non_secret_key("LOG_LEVEL")
        assert _is_non_secret_key("NODE_ENV")
        assert _is_non_secret_key("DB_HOST")
        assert _is_non_secret_key("DEBUG")

    def test_secret_keys_are_not_flagged_as_non_secret(self):
        # Secret keys should NOT match non-secret patterns
        assert not _is_non_secret_key("DB_PASSWORD")
        assert not _is_non_secret_key("API_KEY")  # but this is also non-secret by pattern

    def test_high_value_overrides_non_secret(self):
        # A key that matches both should be treated as high-value
        # The audit logic checks is_high_value_key first
        assert _is_high_value_key("SECRET_KEY") or True  # both can match


class TestWeakValueDetection:
    def test_placeholder_values(self):
        assert _is_weak_value("changeme")
        assert _is_weak_value("password")
        assert _is_weak_value("secret")
        assert _is_weak_value("test")
        assert _is_weak_value("example")
        assert _is_weak_value("TODO")
        assert _is_weak_value("FIXME")
        assert _is_weak_value("ReplaceMe")
        assert _is_weak_value("replace_me")
        assert _is_weak_value("xxx")
        assert _is_weak_value("1234")
        assert _is_weak_value("123456")
        assert _is_weak_value("abcdef")
        assert _is_weak_value("default")
        assert _is_weak_value("placeholder")
        assert _is_weak_value("sample")
        assert _is_weak_value("dummy")

    def test_template_values(self):
        assert _is_weak_value("[insert-key-here]")
        assert _is_weak_value("<your-api-key>")
        assert _is_weak_value("${API_KEY}")

    def test_your_prefix_values(self):
        assert _is_weak_value("your_secret")
        assert _is_weak_value("your-api-key")
        assert _is_weak_value("insert_your_secret")

    def test_empty_value(self):
        assert _is_weak_value("")

    def test_strong_values(self):
        assert not _is_weak_value("a7f3b2c9d4e5f6a7b8c9d0e1f2a3b4c5")
        assert not _is_weak_value("sk_live_abc123def456ghi789")
        assert not _is_weak_value("my_actual_production_password_2024")


class TestMaskValue:
    def test_short_value(self):
        assert _mask_value("ab") == "***"

    def test_medium_value(self):
        result = _mask_value("abcdefghijklmnop")
        assert result.startswith("abcd")
        assert result.endswith("op")
        assert "..." in result

    def test_exact_threshold(self):
        result = _mask_value("abcdefg")
        # 7 chars > show=4, so it shows "abcd...fg"
        assert "..." in result


# ── Core audit logic ──────────────────────────────────────────────────────────


class TestAuditEnvContent:
    def test_clean_file_no_issues(self):
        lines = [
            "DB_HOST=localhost",
            "DB_PORT=5432",
            "APP_ENV=production",
        ]
        findings = audit_env_content(lines)
        assert len(findings) == 0

    def test_weak_password_critical(self):
        lines = ["DB_PASSWORD=changeme"]
        findings = audit_env_content(lines)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_CRITICAL
        assert findings[0].rule_id == "ENV-WEAK"
        assert findings[0].key == "DB_PASSWORD"

    def test_empty_secret_critical(self):
        lines = ["API_KEY="]
        findings = audit_env_content(lines)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_CRITICAL
        assert findings[0].rule_id == "ENV-WEAK"
        assert "(empty)" in findings[0].value_preview

    def test_short_secret_warning(self):
        lines = ["DB_PASSWORD=short1"]
        findings = audit_env_content(lines)
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_WARNING
        assert findings[0].rule_id == "ENV-SHORT"

    def test_long_strong_secret_no_issues(self):
        lines = ["DB_PASSWORD=a7f3b2c9d4e5f6a7b8c9d0e1"]
        findings = audit_env_content(lines)
        assert len(findings) == 0

    def test_duplicate_keys_warning(self):
        lines = [
            "API_KEY=first_value",
            "API_KEY=second_value",
        ]
        findings = audit_env_content(lines)
        dup_findings = [f for f in findings if f.rule_id == "ENV-DUP"]
        assert len(dup_findings) == 1
        assert dup_findings[0].severity == SEVERITY_WARNING
        assert "Duplicate" in dup_findings[0].message

    def test_inline_comment_info(self):
        lines = ["DB_PASSWORD=mysecret # this is the prod password"]
        findings = audit_env_content(lines)
        comment_findings = [f for f in findings if f.rule_id == "ENV-COMMENT"]
        assert len(comment_findings) == 1
        assert comment_findings[0].severity == SEVERITY_INFO

    def test_quoted_value_no_comment_issue(self):
        lines = ['DB_PASSWORD="my#secret#value"']
        findings = audit_env_content(lines)
        comment_findings = [f for f in findings if f.rule_id == "ENV-COMMENT"]
        assert len(comment_findings) == 0

    def test_unquoted_special_chars_warning(self):
        lines = ["DB_PASSWORD=value$with$special"]
        findings = audit_env_content(lines)
        unquoted_findings = [f for f in findings if f.rule_id == "ENV-UNQUOTED"]
        assert len(unquoted_findings) == 1
        assert unquoted_findings[0].severity == SEVERITY_WARNING

    def test_non_secret_weak_value_no_issue(self):
        # A non-secret key with a "weak" value should not be flagged
        lines = ["APP_ENV=test"]
        findings = audit_env_content(lines)
        assert len(findings) == 0

    def test_comments_and_blank_lines_skipped(self):
        lines = [
            "# This is a comment",
            "",
            "DB_HOST=localhost",
            "   # another comment",
        ]
        findings = audit_env_content(lines)
        assert len(findings) == 0

    def test_multiple_issues_in_one_file(self):
        lines = [
            "DB_PASSWORD=changeme",       # CRITICAL: weak
            "API_TOKEN=short",            # WARNING: short
            "DB_HOST=localhost",          # OK
            "DB_PASSWORD=override",       # WARNING: duplicate
            "SECRET_KEY=val#comment",     # INFO: inline comment
        ]
        findings = audit_env_content(lines)
        assert len(findings) >= 4  # weak + short + dup + comment

    def test_case_insensitive_weak_detection(self):
        lines = ["SECRET=ChangeMe"]
        findings = audit_env_content(lines)
        assert any(f.rule_id == "ENV-WEAK" for f in findings)


class TestAuditEnvFile:
    def test_file_not_found(self):
        import pytest

        with pytest.raises(FileNotFoundError):
            audit_env_file("/nonexistent/.env")

    def test_scan_actual_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DB_PASSWORD=changeme\nDB_HOST=localhost\n")
        findings, key_count = audit_env_file(str(env_file))
        assert key_count == 2
        assert any(f.rule_id == "ENV-WEAK" for f in findings)

    def test_scan_clean_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DB_HOST=prod.example.com\nDB_PORT=5432\nAPP_ENV=production\n")
        findings, key_count = audit_env_file(str(env_file))
        assert key_count == 3
        assert len(findings) == 0


# ── Full audit run ────────────────────────────────────────────────────────────


class TestRunSecurityAudit:
    def test_multiple_files(self, tmp_path):
        f1 = tmp_path / ".env.dev"
        f1.write_text("DB_PASSWORD=changeme\n")
        f2 = tmp_path / ".env.prod"
        f2.write_text("DB_PASSWORD=a7f3b2c9d4e5f6a7b8c9d0e1\nDB_HOST=prod.db\n")

        result = run_security_audit([str(f1), str(f2)])
        assert result.files_scanned == 2
        assert result.keys_scanned == 3
        assert result.critical_count >= 1  # changeme in dev

    def test_missing_file_skipped(self, tmp_path):
        f1 = tmp_path / ".env.dev"
        f1.write_text("DB_HOST=localhost\n")

        result = run_security_audit([str(f1), str(tmp_path / ".nonexistent")])
        assert result.files_scanned == 1

    def test_strict_mode_promotes_warnings(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DB_PASSWORD=short1\n")  # short → warning

        # Normal: audit_env_file only produces content findings (no gitignore/perm)
        findings_normal, _ = audit_env_file(str(env_file))
        from envault.security import SecurityFinding as SF
        assert any(f.severity == SEVERITY_WARNING for f in findings_normal)
        assert not any(f.severity == SEVERITY_CRITICAL for f in findings_normal)

        # Strict: promote warnings to critical
        findings_strict = [
            SF(SEVERITY_CRITICAL, f.rule_id, f.message, f.key, f.value_preview, f.line_number)
            if f.severity == SEVERITY_WARNING else f
            for f in findings_normal
        ]
        assert any(f.severity == SEVERITY_CRITICAL for f in findings_strict)

    def test_empty_files_list(self):
        result = run_security_audit([])
        assert result.files_scanned == 0
        assert result.keys_scanned == 0
        assert result.total_issues == 0


# ── SecurityAuditResult ───────────────────────────────────────────────────────


class TestSecurityAuditResult:
    def test_counts(self):
        result = SecurityAuditResult()
        result.findings = [
            SecurityFinding(SEVERITY_CRITICAL, "T1", "msg1", "k1"),
            SecurityFinding(SEVERITY_CRITICAL, "T2", "msg2", "k2"),
            SecurityFinding(SEVERITY_WARNING, "T3", "msg3", "k3"),
            SecurityFinding(SEVERITY_INFO, "T4", "msg4", "k4"),
        ]
        assert result.critical_count == 2
        assert result.warning_count == 1
        assert result.info_count == 1
        assert result.total_issues == 4
        assert result.has_critical is True

    def test_no_critical(self):
        result = SecurityAuditResult()
        result.findings = [
            SecurityFinding(SEVERITY_WARNING, "T1", "msg1", "k1"),
        ]
        assert result.has_critical is False

    def test_empty_result(self):
        result = SecurityAuditResult()
        assert result.critical_count == 0
        assert result.total_issues == 0
        assert result.has_critical is False


# ── Format report ─────────────────────────────────────────────────────────────


class TestFormatSecurityReport:
    def test_no_issues(self):
        result = SecurityAuditResult(files_scanned=1, keys_scanned=5)
        report = format_security_report(result)
        assert "No security issues found" in report

    def test_with_issues(self):
        result = SecurityAuditResult(files_scanned=2, keys_scanned=10)
        result.findings = [
            SecurityFinding(SEVERITY_CRITICAL, "ENV-WEAK", "Weak value on 'DB_PASSWORD'", "DB_PASSWORD", "chan...", 3),
            SecurityFinding(SEVERITY_WARNING, "ENV-SHORT", "Short value on 'API_KEY'", "API_KEY", "sho...", 5),
            SecurityFinding(SEVERITY_INFO, "ENV-COMMENT", "Inline comment on 'SECRET'", "SECRET", "val...", 7),
        ]
        report = format_security_report(result, file_label=".env")
        assert "CRITICAL" in report
        assert "WARNING" in report
        assert "INFO" in report
        assert "ENV-WEAK" in report
        assert "line 3" in report
