"""Tests that every CLI parser's --help output ends with credit_line()."""

import subprocess
import sys

from kuhy_credit import credit_line
import pytest

MODULES_WITH_CLI = [
    "wake_alarm._audit",
    "wake_alarm._ring_wav",
    "wake_alarm._session",
    "wake_alarm._trigger",
    "wake_alarm._sync",
]


def _run_help(module: str) -> str:
    """Run `python -m <module> --help` and return stdout.

    Never falls back to a bare run: `_trigger` without --help could start the
    real morning routine. argparse exits 0 on --help, so check=True holds.
    """
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.mark.parametrize("module", MODULES_WITH_CLI)
def test_help_ends_with_credit_line(module: str) -> None:
    """The --help output must end with credit_line()."""
    help_text = _run_help(module)
    assert help_text.endswith(credit_line() + "\n"), (
        f"Module {module} help does not end with credit_line()"
    )
