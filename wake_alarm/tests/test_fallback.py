"""The fallback tick, the ring lifecycle and the CLI."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
import signal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm import _fallback, _fallback_observe
from wake_alarm._events import last_value
from wake_alarm._fallback_latch import mark_started, read_latch
from wake_alarm._fallback_observe import Observation
from wake_alarm._fallback_policy import Decision, Facts
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

# Bound at import, before the autouse fixture patches it.
REAL_NOW = _fallback._now
DAY = "2026-10-01"
A = datetime(2026, 10, 1, 7, 0).astimezone()


def _session_log() -> list[tuple[str, str]]:
    session = {"date": DAY, "started_at": f"{DAY}T07:20:00", "outcome": "active"}
    raw = {"alarm": {"fields": {"current_session": [session, "h"]}}}
    return [("p", json.dumps(raw))]


@pytest.fixture(autouse=True)
def world() -> Generator[MagicMock]:
    """Alarm 07:00, a tiny WAV pair, and a ring that ends on its first poll."""
    with (
        patch.object(_fallback_observe, "get_alarm", return_value=Alarm(7, 0, "c")),
        patch.object(_fallback, "get_alarm", return_value=Alarm(7, 0, "c")),
        patch.object(_fallback, "ensure_pair", return_value=("r", "l")),
        patch.object(_fallback, "_now", return_value=A + timedelta(minutes=20)),
        patch.object(_fallback, "ring") as ring,
    ):

        def fake_ring(poll: Callable[[], str | None], **_: object) -> str:
            return poll() or "cap"

        ring.side_effect = fake_ring
        yield ring


def _tick(minutes: float, published: list[tuple[str, str]] | None = None) -> Decision:
    with patch.object(_fallback_observe, "fetch_firebase_logs", return_value=published):
        return _fallback.tick(A + timedelta(minutes=minutes))


def test_waiting_logs_the_decision_once(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        assert _tick(1, []) == Decision(ring=False, reason="waiting")
        _tick(1.5, [])
    assert caplog.text.count("fallback_tick:") == 1
    assert last_value("fallback_tick") == f"{DAY}|False|waiting"


def test_phone_silent_rings_until_the_session_starts(
    world: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        patch.object(
            _fallback_observe, "fetch_firebase_logs", side_effect=[[], _session_log()]
        ),
        caplog.at_level(logging.INFO),
    ):
        decision = _fallback.tick(A + timedelta(minutes=3))
    assert decision == Decision(ring=True, reason="phone_silent")
    world.assert_called_once()
    latch = read_latch(DAY)
    assert latch is not None
    assert latch.stop_reason == "session_started"
    assert "fallback_ring_start" in caplog.text
    assert "fallback_ring_stop" in caplog.text
    # Final for the day, even if Firebase goes quiet afterwards.
    assert _tick(25, None) == Decision(ring=False, reason="session_started")


def test_an_open_latch_is_closed_when_the_decision_goes_quiet() -> None:
    mark_started(None, day=DAY, now=A + timedelta(minutes=2), reason="phone_silent")
    assert _tick(10, _session_log()) == Decision(ring=False, reason="session_started")
    latch = read_latch(DAY)
    assert latch is not None
    assert latch.stop_reason == "session_started"


def test_a_crash_mid_ring_still_records_the_stop(world: MagicMock) -> None:
    world.side_effect = SystemExit(143)
    with pytest.raises(SystemExit):
        _tick(3, [])
    latch = read_latch(DAY)
    assert latch is not None
    assert latch.stop_reason == "terminated"


def test_terminate_handler_raises_system_exit() -> None:
    with pytest.raises(SystemExit) as raised:
        _fallback._terminate(signal.SIGTERM, None)
    assert raised.value.code == 128 + signal.SIGTERM


def test_describe_and_show() -> None:
    facts = Facts(now=A, alarm_at=A, free_day=False)
    text = _fallback.describe(
        Observation(facts, reachable=False), Decision(ring=True, reason="x")
    )
    assert "WOULD RING: x" in text
    assert "UNREACHABLE" in text
    assert "quiet: y" in _fallback.describe(
        Observation(facts), Decision(ring=False, reason="y")
    )
    assert "A=07:00" in _fallback.show(A)


class TestCli:
    def test_show(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _fallback.main(["--show"]) == 0
        assert "latch=None" in capsys.readouterr().out

    def test_dry_run_at_changes_nothing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.object(_fallback_observe, "fetch_firebase_logs", return_value=[]):
            assert _fallback.main(["--dry-run", "--at", f"{DAY}T07:05:00"]) == 0
        assert "WOULD RING: phone_silent" in capsys.readouterr().out
        assert read_latch(DAY) is None
        assert last_value("fallback_tick") is None

    def test_at_needs_dry_run(self) -> None:
        with pytest.raises(SystemExit):
            _fallback.main(["--tick", "--at", f"{DAY}T07:05:00"])

    def test_tick_configures_logging_and_signals(self) -> None:
        with (
            patch.object(_fallback, "configure_logging") as configure,
            patch.object(_fallback.signal, "signal") as install,
            patch.object(_fallback, "tick") as tick,
            patch("sys.argv", ["prog", "--tick"]),
        ):
            assert _fallback.main() == 0
        configure.assert_called_once_with(component="fallback")
        install.assert_called_once_with(signal.SIGTERM, _fallback._terminate)
        tick.assert_called_once()

    def test_real_now_is_aware(self) -> None:
        assert REAL_NOW().tzinfo is not None


def test_a_ring_that_keeps_going_until_the_cap() -> None:
    """The first poll finds nothing to stop for; the fake then hits the cap."""
    assert _tick(3, []) == Decision(ring=True, reason="phone_silent")
    latch = read_latch(DAY)
    assert latch is not None
    assert latch.stop_reason == "cap"
    assert last_value("fallback_settled") is None


def test_a_wav_failure_still_closes_the_latch() -> None:
    with (
        patch.object(_fallback, "ensure_pair", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        _tick(3, [])
    latch = read_latch(DAY)
    assert latch is not None
    assert latch.stop_reason == "terminated"
