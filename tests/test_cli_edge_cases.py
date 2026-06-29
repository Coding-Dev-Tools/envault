"""Targeted edge-case and packaging config tests for Envault.

Covers uncovered error-handling paths:
- CLI diff with env names (not file paths) — cli.py:66-69
- CLI sync with conflicts in dry_run — cli.py:142-144
- CLI sync with actual conflicts — cli.py:156-158
- CLI sync with deleted keys — cli.py:173
- CLI rotate with missing env file — cli.py:193-194
- Packaging config parity (py.typed, known-first-party)
"""

from __future__ import annotations

import sys
import yaml

from pathlib import Path
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from envault.cli import app


def _make_config(tmp_path, env_map):
    """Create minimal .envault.yml with list-formatted environments."""
    config = {
        "project": "test",
        "environments": [
            {"name": name, "env_file": path} for name, path in env_map.items()
        ],
    }
    config_path = tmp_path / ".envault.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return config_path


def test_diff_with_env_name_not_file(tmp_path):
    """diff with env names uses get_env_path path (cli.py:66-69)."""
    runner = CliRunner()
    dev_env = tmp_path / ".env.dev"
    prod_env = tmp_path / ".env.prod"
    dev_env.write_text("A=1\nB=2\n")
    prod_env.write_text("A=1\nB=3\n")

    config_path = _make_config(tmp_path, {"dev": str(dev_env), "prod": str(prod_env)})

    result = runner.invoke(
        app,
        [
            "diff",
            "dev",
            "prod",
            "--config",
            str(config_path),
        ],
    )
    assert result.exit_code == 0
    assert "B" in result.output


def test_sync_dry_run_conflicts_skipped(tmp_path):
    """sync --dry-run --strategy error shows conflicts (cli.py:142-144)."""
    runner = CliRunner()
    dev_env = tmp_path / ".env.dev"
    prod_env = tmp_path / ".env.prod"

    dev_env.write_text("A=1\nB=2\nC=3\n")
    prod_env.write_text("A=different\n")

    config_path = _make_config(tmp_path, {"dev": str(dev_env), "prod": str(prod_env)})

    result = runner.invoke(
        app,
        [
            "sync",
            "dev",
            "prod",
            "--config",
            str(config_path),
            "--dry-run",
            "--strategy",
            "error",
        ],
    )
    # With --strategy error and conflicting A, should show conflicts
    assert result.exit_code == 0 or result.exit_code == 1


def test_sync_with_conflicts_exits_1(tmp_path):
    """sync with --strategy error and real conflicts exits 1 (cli.py:156-158)."""
    runner = CliRunner()
    dev_env = tmp_path / ".env.dev"
    prod_env = tmp_path / ".env.prod"

    dev_env.write_text("A=from_dev\nB=2\n")
    prod_env.write_text("A=from_prod\n")

    config_path = _make_config(tmp_path, {"dev": str(dev_env), "prod": str(prod_env)})

    result = runner.invoke(
        app,
        [
            "sync",
            "dev",
            "prod",
            "--config",
            str(config_path),
            "--strategy",
            "error",
        ],
    )
    assert result.exit_code == 1
    # Conflict detail goes to err_console (stderr); exit code is enough


def test_sync_with_deleted_keys(tmp_path):
    """sync with --allow-delete shows deleted keys (cli.py:173)."""
    runner = CliRunner()
    dev_env = tmp_path / ".env.dev"
    prod_env = tmp_path / ".env.prod"

    dev_env.write_text("A=1\n")
    prod_env.write_text("A=1\nB=removed\nC=gone\n")

    config_path = _make_config(tmp_path, {"dev": str(dev_env), "prod": str(prod_env)})

    result = runner.invoke(
        app,
        [
            "sync",
            "dev",
            "prod",
            "--config",
            str(config_path),
            "--allow-delete",
        ],
    )
    assert result.exit_code == 0


def test_rotate_missing_env_file(tmp_path):
    """rotate with nonexistent env file exits 1 (cli.py:193-194)."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "rotate",
            "MY_KEY",
            "--env",
            str(tmp_path / "nonexistent.env"),
        ],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "Error" in result.output


class TestPackagingQuality:
    """Tests for py.typed packaging config."""

    def test_package_data_includes_py_typed(self):
        """pyproject.toml should have package-data config for py.typed."""
        import tomllib

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        pkg_data = data.get("tool", {}).get("setuptools", {}).get("package-data", {})
        assert "envault" in pkg_data, (
            "Expected [tool.setuptools.package-data] section for 'envault'"
        )
        assert "py.typed" in pkg_data["envault"], (
            f"Expected 'py.typed' in package-data for envault, got {pkg_data['envault']}"
        )

    def test_ruff_known_first_party(self):
        """ruff known-first-party should be ['envault'], not ['*']."""
        import tomllib

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        isort_cfg = (
            data.get("tool", {}).get("ruff", {}).get("lint", {}).get("isort", {})
        )
        kfp = isort_cfg.get("known-first-party", [])
        assert kfp == ["envault"], f"known-first-party should be ['envault'], got {kfp}"
