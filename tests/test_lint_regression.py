"""Lint regression tests — guard against specific rule violations.

These tests assert zero violations for a specific ruff rule in a scoped
directory. They fail if a new violation is introduced, providing a durable
regression guard analogous to a behavioral test.
"""

import subprocess
import sys

REPO_ROOT = __file__.rsplit("/", 2)[0] if "/" in __file__ else None
if REPO_ROOT is None:
    REPO_ROOT = __file__.rsplit("\\", 2)[0]


def test_tests_dir_has_zero_f401_violations() -> None:
    """tests/ must have zero F401 (unused-import) violations."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select=F401",
            "--output-format=concise",
            "tests/",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tests/ has F401 violation(s):\n{result.stdout}\n"


def test_tests_dir_has_zero_f841_violations() -> None:
    """tests/ must have zero F841 (unused-variable) violations."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select=F841",
            "--output-format=concise",
            "tests/",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"tests/ has F841 violation(s):\n{result.stdout}\n{result.stderr}"
    )


def test_tests_dir_has_zero_f811_violations() -> None:
    """tests/ must have zero F811 (redefinition) violations."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select=F811",
            "--output-format=concise",
            "tests/",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"tests/ has F811 violation(s):\n{result.stdout}\n{result.stderr}"
    )
