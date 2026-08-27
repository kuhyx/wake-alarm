"""Tests for repeated card-profile reactivation while the alarm rings."""

from __future__ import annotations

import threading
import time

import pytest

from wake_alarm import _reactivate
from wake_alarm._reactivate import (
    reactivate_until_stable,
    start_background_reactivation,
)


@pytest.fixture(autouse=True)
def _fast_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a short, deterministic retry schedule instead of the real one."""
    monkeypatch.setattr(_reactivate, "REACTIVATE_ATTEMPT_DELAYS", (1.0, 2.0))


def test_runs_one_pass_per_scheduled_delay_plus_the_first() -> None:
    """A schedule of two delays means three activation passes."""
    calls: list[int] = []
    reactivate_until_stable(
        lambda: calls.append(1),
        lambda: ["sink"],
        sleep=lambda _d: None,
    )
    assert len(calls) == 3


def test_sleeps_for_each_configured_delay() -> None:
    """The decaying schedule is honoured, not collapsed into a busy loop."""
    slept: list[float] = []
    reactivate_until_stable(
        lambda: None,
        list,
        sleep=slept.append,
    )
    assert slept == [1.0, 2.0]


def test_returns_the_final_sink_set() -> None:
    """The caller learns which outputs ended up present."""
    result = reactivate_until_stable(
        lambda: None,
        lambda: ["a", "b"],
        sleep=lambda _d: None,
    )
    assert result == frozenset({"a", "b"})


def test_reports_a_sink_that_appears_late(caplog: pytest.LogCaptureFixture) -> None:
    """The HDMI case: a sink absent at first must be announced when it lands."""
    sequence = [["analog"], ["analog"], ["analog", "hdmi"]]
    result = reactivate_until_stable(
        lambda: None,
        lambda: sequence.pop(0),
        sleep=lambda _d: None,
    )
    assert result == frozenset({"analog", "hdmi"})
    assert "hdmi" in caplog.text


def test_every_pass_logs_the_enumerated_sinks(caplog: pytest.LogCaptureFixture) -> None:
    """Each pass records what it saw, so a silent alarm is diagnosable."""
    with caplog.at_level("INFO"):
        reactivate_until_stable(
            lambda: None,
            lambda: ["analog"],
            sleep=lambda _d: None,
        )
    assert caplog.text.count("Sink reactivation pass") == 3


def test_logs_none_when_no_sink_is_present(caplog: pytest.LogCaptureFixture) -> None:
    """An empty enumeration is stated explicitly rather than logged blank."""
    with caplog.at_level("INFO"):
        reactivate_until_stable(lambda: None, list, sleep=lambda _d: None)
    assert "(none)" in caplog.text


def test_stop_event_ends_retrying_before_the_sleep() -> None:
    """Dismissing the alarm stops the retry loop promptly."""
    stop = threading.Event()
    stop.set()
    calls: list[int] = []
    reactivate_until_stable(
        lambda: calls.append(1),
        list,
        sleep=lambda _d: None,
        stop=stop,
    )
    assert len(calls) == 1


def test_stop_event_set_during_the_sleep_ends_retrying() -> None:
    """A dismissal landing mid-delay is noticed on wake, not ignored."""
    stop = threading.Event()
    calls: list[int] = []
    reactivate_until_stable(
        lambda: calls.append(1),
        list,
        sleep=lambda _d: stop.set(),
        stop=stop,
    )
    assert len(calls) == 1


def test_background_thread_runs_the_passes() -> None:
    """The helper actually executes the work off the beep loop's thread."""
    done = threading.Event()
    stop = threading.Event()
    thread = start_background_reactivation(
        done.set,
        lambda: ["s"],
        sleep=lambda _d: None,
        stop=stop,
    )
    thread.join(timeout=5)
    assert done.is_set()


def test_background_thread_is_a_daemon() -> None:
    """A stuck retry must never keep the process alive after dismissal."""
    stop = threading.Event()
    stop.set()
    thread = start_background_reactivation(
        lambda: None,
        list,
        sleep=lambda _d: None,
        stop=stop,
    )
    thread.join(timeout=5)
    assert thread.daemon


def test_activate_only_discards_the_captured_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry passes must not hand back a state anyone could restore.

    Only the *first* activation sees the user's real audio settings; every
    later pass captures the alarm's own. Returning one would let a future
    caller restore the alarm's settings as if they were the user's.
    """
    calls: list[str] = []

    def fake_activate() -> str:
        calls.append("activated")
        return "prior-state"

    monkeypatch.setattr(_reactivate, "_activate_all_outputs", fake_activate)
    _reactivate._activate_outputs_only()
    assert calls == ["activated"]


def test_list_sinks_now_returns_the_real_sinks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The zero-arg adapter resolves pactl and forwards the path."""
    monkeypatch.setattr(_reactivate, "_pactl_path", lambda: "/usr/bin/pactl")
    monkeypatch.setattr(
        _reactivate,
        "_list_real_sinks",
        lambda pactl: [f"sink-via-{pactl}"],
    )
    assert _reactivate._list_real_sinks_now() == ["sink-via-/usr/bin/pactl"]


def test_list_sinks_now_is_empty_without_pactl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A machine with no pactl reports no sinks instead of raising.

    The adapter runs on a background thread nobody is watching, so an
    exception there would vanish silently.
    """
    monkeypatch.setattr(_reactivate, "_pactl_path", lambda: None)
    assert _reactivate._list_real_sinks_now() == []


def test_start_alarm_reactivation_binds_the_real_callables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one wiring point passes the real pactl adapters and time.sleep."""
    captured: dict[str, object] = {}

    sentinel = threading.Thread(target=lambda: None)

    def fake_start(
        activate: object,
        list_sinks: object,
        *,
        sleep: object,
        stop: object,
    ) -> threading.Thread:
        captured.update(
            activate=activate, list_sinks=list_sinks, sleep=sleep, stop=stop
        )
        return sentinel

    monkeypatch.setattr(_reactivate, "start_background_reactivation", fake_start)
    stop = threading.Event()

    assert _reactivate.start_alarm_reactivation(stop) is sentinel

    assert captured["activate"] is _reactivate._activate_outputs_only
    assert captured["list_sinks"] is _reactivate._list_real_sinks_now
    assert captured["sleep"] is time.sleep
    assert captured["stop"] is stop
