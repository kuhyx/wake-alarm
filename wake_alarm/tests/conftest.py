"""Shared fixtures keeping the wake_alarm suite off the real machine.

Two hazards are left now that the PC no longer owns a lock screen, audio or
an inhibitor:

* ``_state`` signs its records with gatelock's HMAC key, and the real key is
  root-owned but *world-readable*. An unpatched run would sign test entries
  with the **production** key on this machine and with none at all anywhere
  else, so the suite would pass here and behave differently in CI.
* ``WAKE_STATE_FILE`` is a real path inside the repo, and ``_trigger`` now
  *writes* it. The trigger tests never redirected it, because until the
  once-per-day latch moved into the trigger nothing on that path wrote
  anything. Redirecting it here rather than per-file is deliberate: a
  per-file redirect is exactly the kind that gets forgotten when a new writer
  appears, and the failure is silent -- a green suite that quietly stamped
  the live state file.
* ``_logging_setup`` attaches a JSONL sink to the root logger the first time
  any entry point's ``main()`` runs, pointed at the real
  ``~/.local/state/wake_alarm/events.jsonl``. Unredirected, every suite run
  appended fixture warnings ("Synced alarm out of range: 24:0") to the log a
  failed wake-up is reconstructed from.
* The free-day and sick-day pools live under ``~/.local/share``; both are
  redirected, and the sick-day sync is stubbed offline.
* Wake enforcement v2 writes more state (the fallback latch, the event
  state, incident reports) and reaches real hardware (``pw-play``,
  ``sudo systemctl``, ``rtcwake``, ``journalctl``). Every path is redirected
  and every process seam raises unless a test replaces it, so no test can
  ring this machine's speakers or arm its RTC.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING
from unittest.mock import patch

import freedays
import pytest
import sickdays

from wake_alarm import _session_strip

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def _no_process(cmd: list[str]) -> object:
    """Stand-in for every process seam: an unmocked test fails loudly."""
    msg = f"test tried to run {cmd!r}"
    raise AssertionError(msg)


class FakeClock:
    """A monotonic clock that only moves when ``sleep`` is called.

    Pass ``clock.sleep`` and ``clock.now`` to ``_session.refresh`` so a dead
    backend burns its 150 s retry budget instantly instead of for real.
    """

    def __init__(self) -> None:
        self.elapsed = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        """Seconds elapsed on the fake clock."""
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        """Advance the clock without waiting."""
        self.sleeps.append(seconds)
        self.elapsed += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    """A fresh :class:`FakeClock`."""
    return FakeClock()


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path) -> Generator[None]:
    """Keep signing keys, state writes and processes inside ``tmp_path``."""
    key_file = tmp_path / "hmac.key"
    key_file.write_bytes(b"0" * 32)
    # An ExitStack, not one `with (...)`: Python caps a statement at 20
    # nested blocks, and every patch is one.
    patches = [
        patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key_file),
        patch("wake_alarm._state.WAKE_STATE_FILE", tmp_path / "wake_state.json"),
        # _logging_setup imported these by value, so patch its names, not
        # _constants'.
        patch("wake_alarm._logging_setup.LOG_JSONL_FILE", tmp_path / "events.jsonl"),
        patch("wake_alarm._logging_setup.LOG_DEDUPE_FILE", tmp_path / "last.json"),
        patch(
            "wake_alarm._session.MORNING_SESSION_FILE",
            tmp_path / "morning_session.json",
        ),
        # The strip imported the path by value too; its tick re-reads it every
        # second, its refresh spawns systemctl, and its warn-once memory must
        # not leak from one test into the next.
        patch(
            "wake_alarm._session_strip.MORNING_SESSION_FILE",
            tmp_path / "morning_session.json",
        ),
        patch("wake_alarm._session_strip._popen", _no_process),
        patch("wake_alarm._session_strip._once", _session_strip._Once()),
        patch(
            "wake_alarm._workday_penalty.WORKDAY_PENALTY_FILE",
            tmp_path / "workday_penalty.json",
        ),
        # Read by every get_alarm() the v2 modules make; the live file is
        # the trigger's cache. A missing Firebase config keeps fetches
        # off the network unless a test patches the fetch itself.
        patch("wake_alarm._sync.ALARM_CACHE_FILE", tmp_path / "alarm_cache.json"),
        patch(
            "wake_alarm._sync_transport.FIREBASE_CONFIG_FILE",
            tmp_path / "no-firebase.json",
            create=True,
        ),
        patch("wake_alarm._events.EVENT_STATE_FILE", tmp_path / "event_state.json"),
        patch(
            "wake_alarm._fallback_latch.FALLBACK_RING_FILE",
            tmp_path / "fallback_ring.json",
        ),
        patch("wake_alarm._pc_wake_mode.PC_WAKE_CONFIG", tmp_path / "pc_wake.json"),
        patch("wake_alarm._audit.INCIDENTS_DIR", tmp_path / "incidents"),
        patch("wake_alarm._audit_sources.LOG_JSONL_FILE", tmp_path / "audit.jsonl"),
        patch("wake_alarm._fallback.SYSTEM_WAV_DIR", tmp_path / "wav-system"),
        patch("wake_alarm._fallback.USER_WAV_DIR", tmp_path / "wav-user"),
        patch("wake_alarm._rtc_hw.WAKEALARM_FILE", tmp_path / "wakealarm"),
        patch("wake_alarm._rtc_hw.RTC_ARMED_FILE", tmp_path / "rtc_armed.json"),
        patch("wake_alarm._ring_player._run", _no_process),
        patch("wake_alarm._ring_player._popen", _no_process),
        patch("wake_alarm._rtc_hw._run", _no_process),
        patch("wake_alarm._audit_sources._run", _no_process),
        # The shared free-day pool lives under ~/.local/share, outside every
        # path above. Without this, a real free day on the developer's
        # machine would silence the alarm in every trigger test here.
        patch(
            "freedays._api.resolve_paths",
            lambda paths: paths or freedays.Paths.under(tmp_path / "freedays"),
        ),
        # Same for the sick-day pool. Its sync is stubbed to "offline": the
        # real ~/.config/crdt-sync credential exists on this machine, so an
        # unstubbed act-mode tick would talk to live Firebase and rewrite the
        # real pool.
        patch(
            "sickdays._api.resolve_paths",
            lambda paths: paths or sickdays.Paths.under(tmp_path / "sickdays"),
        ),
        patch("sickdays.sync_quietly", lambda **_: False),
    ]
    with ExitStack() as stack:
        for redirect in patches:
            stack.enter_context(redirect)
        yield
