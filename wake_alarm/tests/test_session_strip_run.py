"""The corner strip's refresher and its main loop, on a fake Tk."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import timedelta
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

from gatelock.corner_strip import StripContent
import pytest

from wake_alarm import _session_strip
from wake_alarm.tests.test_strip_support import (
    NOW,
    Display,
    Procs,
    signed,
    write,
)

if TYPE_CHECKING:
    from collections.abc import Generator


class TestRefresher:
    @pytest.fixture
    def procs(self) -> Procs:
        fake = Procs()
        with patch("wake_alarm._session_strip._popen", fake):
            yield fake

    def test_first_refresh_is_thirty_seconds_in(self, procs: Procs) -> None:
        refresher = _session_strip.Refresher(start=100.0)
        refresher.tick(129.0)
        assert procs.started == []
        refresher.tick(130.0)
        assert procs.started == [
            ["systemctl", "--user", "start", "--no-block", "wake-alarm-session.service"]
        ]

    def test_one_start_per_interval(self, procs: Procs) -> None:
        refresher = _session_strip.Refresher(start=0.0)
        for second in range(30, 60):
            refresher.tick(float(second))
            procs.procs[-1].poll.return_value = 0
        assert len(procs.started) == 1
        refresher.tick(60.0)
        assert len(procs.started) == 2

    def test_no_second_spawn_while_the_first_runs(self, procs: Procs) -> None:
        refresher = _session_strip.Refresher(start=0.0)
        refresher.tick(30.0)
        refresher.tick(60.0)
        refresher.tick(95.0)
        assert len(procs.started) == 1
        procs.procs[0].poll.return_value = 0
        refresher.tick(96.0)
        assert len(procs.started) == 2

    def test_failed_exit_warns(
        self, procs: Procs, caplog: pytest.LogCaptureFixture
    ) -> None:
        refresher = _session_strip.Refresher(start=0.0)
        refresher.tick(30.0)
        procs.procs[0].poll.return_value = 5
        with caplog.at_level(logging.WARNING):
            refresher.tick(31.0)
        assert "exited 5" in caplog.text

    def test_spawn_failure_warns_and_waits_for_the_next_interval(
        self, procs: Procs, caplog: pytest.LogCaptureFixture
    ) -> None:
        procs.error = FileNotFoundError("systemctl")
        refresher = _session_strip.Refresher(start=0.0)
        with caplog.at_level(logging.WARNING):
            refresher.tick(30.0)
            refresher.tick(31.0)
        assert caplog.text.count("could not start") == 1
        procs.error = None
        refresher.tick(60.0)
        assert len(procs.started) == 1


@pytest.fixture
def display(monkeypatch: pytest.MonkeyPatch) -> Generator[Display]:
    """A fake Tk world with a pinned clock and a recording ``_popen``."""
    fake = Display()
    monkeypatch.setattr("wake_alarm._session_strip._local_now", lambda: NOW)
    monkeypatch.setattr("wake_alarm._session_strip._monotonic", lambda: 0.0)
    monkeypatch.setattr("wake_alarm._session_strip._popen", Procs())
    with ExitStack() as stack:
        for item in fake.patches():
            stack.enter_context(item)
        yield fake


class TestMain:
    def test_nothing_to_show_exits_zero_without_a_window(
        self, display: Display, caplog: pytest.LogCaptureFixture
    ) -> None:
        write(signed(outcome="completed"))
        with caplog.at_level(logging.INFO):
            assert _session_strip.main() == 0
        display.root.mainloop.assert_not_called()
        assert display.built == []
        assert "completed" in caplog.text

    def test_missing_file_exits_zero(self, display: Display) -> None:
        assert _session_strip.main() == 0
        assert display.built == []

    def test_no_output_is_a_warning_and_a_failure(
        self, display: Display, caplog: pytest.LogCaptureFixture
    ) -> None:
        write(signed())
        display.rect = None
        with caplog.at_level(logging.WARNING):
            assert _session_strip.main() == 1
        assert "no live output" in caplog.text
        display.root.destroy.assert_called_once()

    def test_shows_then_closes_when_the_session_completes(
        self, display: Display
    ) -> None:
        write(signed())

        def flip(tick: int) -> None:
            if tick == 3:
                write(signed(outcome="completed", next_step=None))

        display.on_tick = flip
        assert _session_strip.main() == 0
        assert display.built == [
            StripContent(
                "● ◉ ○ ○",
                ("◷ 08:45",),
            )
        ]
        assert display.ticks == 3
        display.window.destroy.assert_called_once()
        display.root.quit.assert_called_once()
        display.root.destroy.assert_called_once()

    def test_closes_when_the_exemption_ends(
        self, display: Display, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write(signed())

        def expire(tick: int) -> None:
            if tick == 2:
                monkeypatch.setattr(
                    "wake_alarm._session_strip._local_now",
                    lambda: NOW + timedelta(minutes=45),
                )

        display.on_tick = expire
        assert _session_strip.main() == 0
        assert display.ticks == 2

    def test_refresh_starts_while_visible_and_not_after_close(
        self, display: Display, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        procs = Procs()
        clock = {"t": 0.0}
        monkeypatch.setattr("wake_alarm._session_strip._popen", procs)
        monkeypatch.setattr("wake_alarm._session_strip._monotonic", lambda: clock["t"])
        write(signed())

        def advance(tick: int) -> None:
            clock["t"] = tick * 10.0
            if tick == 4:
                write(signed(outcome="completed"))

        display.on_tick = advance
        assert _session_strip.main() == 0
        # Ticks run at t=10, 20, 30 (refresh due), then 40 closes the strip.
        assert len(procs.started) == 1

    def test_unopenable_display_is_logged_and_fails(
        self, display: Display, caplog: pytest.LogCaptureFixture
    ) -> None:
        import tkinter as tk

        write(signed())
        with (
            patch(
                "wake_alarm._session_strip._make_root",
                side_effect=tk.TclError("no display"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            assert _session_strip.main() == 1
        assert "no display" in caplog.text
