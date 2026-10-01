"""pc_wake.json: hibernate unless it clearly says poweroff."""

from __future__ import annotations

import json

import pytest

from wake_alarm import _pc_wake_mode
from wake_alarm._pc_wake_mode import main, read_mode


def test_missing_file_is_hibernate() -> None:
    assert read_mode() == "hibernate"


def test_poweroff_is_honoured() -> None:
    _pc_wake_mode.PC_WAKE_CONFIG.write_text(json.dumps({"mode": "poweroff"}))
    assert read_mode() == "poweroff"


@pytest.mark.parametrize(
    "body", ["{bad", "[]", '{"mode": "suspend"}', '{"mode": null}']
)
def test_anything_odd_is_hibernate(body: str) -> None:
    _pc_wake_mode.PC_WAKE_CONFIG.write_text(body)
    assert read_mode() == "hibernate"


def test_cli_prints_the_mode(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert capsys.readouterr().out == "hibernate\n"
