"""The corner strip's content rules, file reader and thin seams."""

from __future__ import annotations

from datetime import UTC, timedelta
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

from gatelock.corner_strip import StripContent
import pytest

from wake_alarm import _session_strip
from wake_alarm.tests.test_strip_support import NOW, STEP, signed

if TYPE_CHECKING:
    from pathlib import Path

# conftest replaces _popen for every test; the real one is captured at import.
REAL_POPEN = _session_strip._popen


class TestStripContent:
    def test_in_progress_says_next_step_and_when_locks_return(self) -> None:
        assert _session_strip.strip_content(signed(), NOW) == StripContent(
            "Morning session not finished",
            (f"Next: {STEP}", "Locks return at 08:45"),
        )

    def test_next_step_null_drops_the_next_line(self) -> None:
        content = _session_strip.strip_content(signed(next_step=None), NOW)
        assert content == StripContent(
            "Morning session not finished", ("Locks return at 08:45",)
        )

    def test_exempt_until_is_shown_in_local_time(self) -> None:
        utc = (NOW + timedelta(minutes=45)).astimezone(UTC).isoformat()
        content = _session_strip.strip_content(signed(exempt_until=utc), NOW)
        assert content is not None
        assert content.lines[-1] == "Locks return at 08:45"

    @pytest.mark.parametrize("outcome", ["completed", "failed", "none", "weird"])
    def test_other_outcomes_show_nothing(self, outcome: str) -> None:
        assert _session_strip.strip_content(signed(outcome=outcome), NOW) is None

    def test_yesterday_shows_nothing(self) -> None:
        assert _session_strip.strip_content(signed(date="2026-11-07"), NOW) is None

    def test_expired_shows_nothing(self) -> None:
        later = NOW + timedelta(minutes=45)
        assert _session_strip.strip_content(signed(), later) is None

    def test_tampered_shows_nothing(self) -> None:
        entry = signed()
        entry["next_step"] = "Something else"
        assert _session_strip.strip_content(entry, NOW) is None

    def test_unsigned_shows_nothing(self) -> None:
        entry = signed()
        del entry["hmac"]
        assert _session_strip.strip_content(entry, NOW) is None

    def test_missing_entry_shows_nothing(self) -> None:
        assert _session_strip.strip_content(None, NOW) is None

    @pytest.mark.parametrize("until", [None, 5, "garbage", "2026-11-08T09:00:00"])
    def test_unusable_exempt_until_shows_nothing(self, until: object) -> None:
        assert _session_strip.strip_content(signed(exempt_until=until), NOW) is None

    @pytest.mark.parametrize("step", [5, ""])
    def test_unusable_next_step_is_left_out(self, step: object) -> None:
        content = _session_strip.strip_content(signed(next_step=step), NOW)
        assert content is not None
        assert content.lines == ("Locks return at 08:45",)


class TestReadEntry:
    def test_missing_file_is_none_and_quiet(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            assert _session_strip.read_entry() is None
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_reads_the_file(self) -> None:
        entry = signed()
        _session_strip.MORNING_SESSION_FILE.write_text(json.dumps(entry))
        assert _session_strip.read_entry() == entry

    @pytest.mark.parametrize("text", ["{nope", "[1, 2]"])
    def test_unreadable_file_warns_once_per_state(
        self, text: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        _session_strip.MORNING_SESSION_FILE.write_text(text)
        with caplog.at_level(logging.WARNING):
            assert _session_strip.read_entry() is None
            assert _session_strip.read_entry() is None
        assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1

    def test_directory_in_the_way_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        _session_strip.MORNING_SESSION_FILE.mkdir()
        with caplog.at_level(logging.WARNING):
            assert _session_strip.read_entry() is None
        assert "Cannot read" in caplog.text


class TestHelpers:
    def test_local_now_is_aware(self) -> None:
        assert _session_strip._local_now().tzinfo is not None

    def test_monotonic_moves_forward(self) -> None:
        first = _session_strip._monotonic()
        assert _session_strip._monotonic() >= first

    def test_make_root_builds_a_withdrawn_tk_root(self) -> None:
        with patch("wake_alarm._session_strip.tk.Tk") as tk_root:
            root = _session_strip._make_root()
        root.withdraw.assert_called_once()
        assert root is tk_root.return_value

    def test_popen_runs_the_command(self) -> None:
        with patch("wake_alarm._session_strip.subprocess.Popen") as popen:
            REAL_POPEN(["true"])
        popen.assert_called_once_with(["true"])

    def test_log_state_path_is_the_conftest_scratch(self, tmp_path: Path) -> None:
        assert _session_strip.MORNING_SESSION_FILE.parent == tmp_path
