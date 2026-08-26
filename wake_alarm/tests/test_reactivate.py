"""Tests for repeated card-profile reactivation while the alarm rings."""

from __future__ import annotations

import threading

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
