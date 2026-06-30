"""Standalone test to reproduce COM-367 behavior."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from envault.cli import app


def test_scan_hardcoded_credential_repro():
    """Exact reproduction of test_scan_hardcoded_credential."""
    runner = CliRunner()
    td = Path(tempfile.mkdtemp())
    env_file = td / ".env"
    env_file.write_text("AWS_ACCESS_KEY_ID=AKIAIO...MPLE\n")
    result = runner.invoke(app, ["scan", str(env_file), "--no-permissions", "--no-gitignore"])
    print(f"exit_code: {result.exit_code}")
    print(f"output: {result.output}")
    print(f"hardcoded_credential in output: {'hardcoded_credential' in result.output}")
    assert result.exit_code == 1, f"Expected exit_code 1, got {result.exit_code}"
    assert "hardcoded_credential" in result.output, "'hardcoded_credential' not in output"


def test_scan_weak_password_repro():
    """Exact reproduction of test_scan_weak_password."""
    runner = CliRunner()
    td = Path(tempfile.mkdtemp())
    env_file = td / ".env"
    env_file.write_text("DB_PASSWORD=password\n")
    result = runner.invoke(app, ["scan", str(env_file), "--no-permissions", "--no-gitignore"])
    print(f"exit_code: {result.exit_code}")
    print(f"output: {result.output}")
    assert "weak_secret" in result.output, "'weak_secret' not in output"


def test_scan_json_output_repro():
    """Exact reproduction of test_scan_json_output."""
    import json as _json

    runner = CliRunner()
    td = Path(tempfile.mkdtemp())
    env_file = td / ".env"
    env_file.write_text("AWS_ACCESS_KEY_ID=AKIAIO...MPLE\n")
    result = runner.invoke(app, ["scan", str(env_file), "--json", "--no-permissions", "--no-gitignore"])
    print(f"exit_code: {result.exit_code}")
    print(f"output: {result.output!r}")
    parsed = _json.loads(result.output.replace("\r\n", "\n").replace("\r", ""), strict=False)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    entry = parsed[0]
    assert "file" in entry
    assert "pass_fail" in entry
    assert "issues" in entry
    assert entry["pass_fail"] == "FAIL"
    assert entry["critical"] >= 1
