"""Shared fakes for the corner-strip tests: signed entries, Tk and Popen."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock.corner_strip import CornerStrip, StripContent
from gatelock.log_integrity import compute_entry_hmac

from wake_alarm import _session_strip

if TYPE_CHECKING:
    from collections.abc import Callable

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 11, 8, 8, 0, tzinfo=TZ)
STEP = "Shower, then tap the bathroom tag again"


def signed(**overrides: object) -> dict[str, object]:
    """A verified in-progress entry for NOW's day, with fields overridden."""
    entry: dict[str, object] = {
        "date": "2026-11-08",
        "outcome": "in_progress",
        "exempt_until": (NOW + timedelta(minutes=45)).isoformat(),
        "next_step": STEP,
    }
    entry.update(overrides)
    entry["hmac"] = compute_entry_hmac(entry)
    return entry


class Procs:
    """A fake ``_popen`` recording starts; each proc finishes when told."""

    def __init__(self) -> None:
        self.started: list[list[str]] = []
        self.procs: list[MagicMock] = []
        self.error: OSError | None = None

    def __call__(self, cmd: list[str]) -> MagicMock:
        if self.error is not None:
            raise self.error
        self.started.append(cmd)
        proc = MagicMock()
        proc.poll.return_value = None
        self.procs.append(proc)
        return proc


class Display:
    """A fake Tk world: records the strip's tick callbacks and drives them."""

    def __init__(self) -> None:
        self.root = MagicMock(name="root")
        self.window = MagicMock(name="window")
        self.callbacks: list[Callable[[], None]] = []
        self.window.after.side_effect = self._after
        self.root.quit.side_effect = self.callbacks.clear
        self.root.mainloop.side_effect = self._mainloop
        self.ticks = 0
        self.on_tick: Callable[[int], None] = lambda _n: None
        self.rect: object = MagicMock(name="rect")
        self.built: list[StripContent] = []

    def _after(self, _ms: int, callback: Callable[[], None]) -> str:
        self.callbacks.append(callback)
        return "job"

    def _mainloop(self) -> None:
        while self.callbacks:
            self.ticks += 1
            self.on_tick(self.ticks)
            self.callbacks.pop(0)()
            if self.ticks > 50:  # runaway-loop guard
                msg = "strip never closed"
                raise AssertionError(msg)

    def build(
        self, _root: object, _config: object, content: StripContent, **kwargs: object
    ) -> object:

        assert kwargs["rect"] is self.rect
        self.built.append(content)
        return CornerStrip(self.window, MagicMock(), [MagicMock(), MagicMock()])

    def patches(self) -> list[object]:
        return [
            patch("wake_alarm._session_strip._make_root", return_value=self.root),
            patch("wake_alarm._session_strip.enumerate_outputs"),
            patch(
                "wake_alarm._session_strip.corner_rect",
                side_effect=lambda _scan: self.rect,
            ),
            patch("wake_alarm._session_strip.build_corner_strip", self.build),
        ]


def write(entry: dict[str, object]) -> None:
    _session_strip.MORNING_SESSION_FILE.write_text(json.dumps(entry))
