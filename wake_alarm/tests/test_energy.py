"""The PC-side reader for the phone's morning energy tap."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from wake_alarm._energy import Energy, latest_energy, main, newest_energy

if TYPE_CHECKING:
    import pytest


def _log(
    level: object, hlc: str = "2026-09-19T06:20:00.000Z-0000-phone", **extra: object
) -> str:
    value = {"date": "2026-09-19", "level": level, **extra}
    return json.dumps({"alarm": {"fields": {"latest_energy": [value, hlc]}}})


class TestNewestEnergy:
    """Ranking and parsing across devices."""

    def test_picks_the_newest_stamp(self) -> None:
        published = [
            ("old", _log(2, "2026-09-10T06:20:00.000Z-0000-old")),
            ("new", _log(4, "2026-09-19T06:20:00.000Z-0000-new")),
        ]
        assert newest_energy(published) == Energy("2026-09-19", 4, "new")
        assert newest_energy(list(reversed(published))) == Energy(
            "2026-09-19", 4, "new"
        )

    def test_device_id_breaks_an_exact_tie(self) -> None:
        published = [("b", _log(3)), ("a", _log(1))]
        assert newest_energy(published) == Energy("2026-09-19", 3, "b")

    def test_skips_every_malformed_shape(self) -> None:
        """Only a 1-5 int with a date string counts; never a bool or 0/6."""
        bad = [
            ("json", "not json"),
            ("list", "[1]"),
            ("no-alarm", "{}"),
            ("no-fields", json.dumps({"alarm": {}})),
            ("no-pair", json.dumps({"alarm": {"fields": {}}})),
            ("empty-pair", json.dumps({"alarm": {"fields": {"latest_energy": []}}})),
            ("not-dict", json.dumps({"alarm": {"fields": {"latest_energy": [3]}}})),
            (
                "no-date",
                json.dumps({"alarm": {"fields": {"latest_energy": [{"level": 3}]}}}),
            ),
            ("bool", _log(level=True)),
            ("float", _log(3.5)),
            ("low", _log(0)),
            ("high", _log(6)),
        ]
        assert newest_energy(bad) is None
        assert newest_energy([*bad, ("ok", _log(5))]) == Energy("2026-09-19", 5, "ok")


class TestLatestEnergy:
    """The fetch wrapper and the CLI."""

    def test_unreadable_backend_is_none(self) -> None:
        with patch("wake_alarm._field_reader.fetch_firebase_logs", return_value=None):
            assert latest_energy() is None

    def test_no_rating_yet_is_none(self) -> None:
        with patch("wake_alarm._field_reader.fetch_firebase_logs", return_value=[]):
            assert latest_energy() is None

    def test_main_prints_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch(
            "wake_alarm._field_reader.fetch_firebase_logs",
            return_value=[("p", _log(3))],
        ):
            assert main() == 0
        assert json.loads(capsys.readouterr().out) == {"date": "2026-09-19", "level": 3}

    def test_main_exits_1_with_nothing(self) -> None:
        with patch("wake_alarm._field_reader.fetch_firebase_logs", return_value=None):
            assert main() == 1
