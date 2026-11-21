"""Tests that every CLI parser's --help output ends with credit_line()."""

import subprocess
import sys

import pytest

from kuhy_credit import credit_line

MODULES_WITH_CLI = [
    "wake_alarm._audit",
    "wake_alarm._ring_wav",
    "wake_alarm._session",
    "wake_alarm._trigger",
    "wake_alarm._sync",
]


def _run_help(module: str) -> str:
    """Run `python -m <module> --help` and return stdout."""
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Some modules need a subcommand; mode_parser is one. Try without --help.
        result = subprocess.run(
            [sys.executable, "-m", module],
            capture_output=True,
            text=True,
        )
    return result.stdout


@pytest.mark.parametrize("module", MODULES_WITH_CLI)
def test_help_ends_with_credit_line(module: str):
    """The --help output must end with credit_line()."""
    help_text = _run_help(module)
    assert help_text.endswith(credit_line() + "\n"), (
        f"Module {module} help does not end with credit_line()"
    )