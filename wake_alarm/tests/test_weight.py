"""The PC-side reader for the phone's morning weigh-in."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from wake_alarm._weight import Weight, latest_weight, main, newest_weight

if TYPE_CHECKING:
    import pytest


def _log(
    kg: object, hlc: str = "2026-09-17T06:20:00.000Z-0000-phone", **extra: object
) -> str:
    value = {"date": "2026-09-17", "kg": kg, **extra}
    return json.dumps({"alarm": {"fields": {"latest_weight_kg": [value, hlc]}}})


class TestNewestWeight:
    """Ranking and parsing across devices."""

    def test_picks_the_newest_stamp(self) -> None:
        """The later HLC wins regardless of listing order."""
        published = [
            ("old", _log(70.0, "2026-09-10T06:20:00.000Z-0000-old")),
            ("new", _log(72.4, "2026-09-17T06:20:00.000Z-0000-new")),
        ]
        assert newest_weight(published) == Weight("2026-09-17", 72.4, "new")
        assert newest_weight(list(reversed(published))) == Weight(
            "2026-09-17", 72.4, "new"
        )

    def test_device_id_breaks_an_exact_tie(self) -> None:
        """Two stamps in the same millisecond do not alternate."""
        published = [("b", _log(71)), ("a", _log(70))]
        assert newest_weight(published) == Weight("2026-09-17", 71.0, "b")

    def test_skips_every_malformed_shape(self) -> None:
        """Garbage never wins, and never crashes."""
        published = [
            ("junk", "{not json"),
            ("list", "[1, 2]"),
            ("no-record", json.dumps({})),
            ("no-fields", json.dumps({"alarm": 1})),
            ("no-pair", json.dumps({"alarm": {"fields": {}}})),
            ("empty-pair", json.dumps({"alarm": {"fields": {"latest_weight_kg": []}}})),
            (
                "scalar",
                json.dumps({"alarm": {"fields": {"latest_weight_kg": [72, "h"]}}}),
            ),
            ("bool-kg", _log(kg=True)),
            ("str-kg", _log("72")),
            (
                "no-date",
                json.dumps(
                    {"alarm": {"fields": {"latest_weight_kg": [{"kg": 1}, "h"]}}}
                ),
            ),
        ]
        assert newest_weight(published) is None
        assert newest_weight([*published, ("ok", _log(72))]) == Weight(
            "2026-09-17", 72.0, "ok"
        )

    def test_an_unstamped_pair_still_parses(self) -> None:
        """A pair with no HLC sorts last but is not thrown away."""
        raw = json.dumps(
            {
                "alarm": {
                    "fields": {"latest_weight_kg": [{"date": "2026-09-01", "kg": 69}]}
                }
            }
        )
        assert newest_weight([("x", raw)]) == Weight("2026-09-01", 69.0, "x")


class TestLatestWeight:
    """The fetch-and-rank entry point and its CLI."""

    def test_unreadable_backend_is_none(self) -> None:
        """No Firebase means no weight, not an error."""
        with patch("wake_alarm._weight.fetch_firebase_logs", return_value=None):
            assert latest_weight() is None
            assert main() == 1

    def test_no_weigh_in_yet_is_none(self) -> None:
        """A phone that has not run a session publishes no weight."""
        logs = [("phone", json.dumps({"alarm": {"fields": {"alarm_hour": [8, "h"]}}}))]
        with patch("wake_alarm._weight.fetch_firebase_logs", return_value=logs):
            assert latest_weight() is None

    def test_main_prints_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The CLI emits one JSON line diet-guard can consume."""
        with patch(
            "wake_alarm._weight.fetch_firebase_logs", return_value=[("p", _log(72.4))]
        ):
            assert main() == 0
        assert json.loads(capsys.readouterr().out) == {"date": "2026-09-17", "kg": 72.4}
