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
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import freedays
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path) -> Generator[None]:
    """Keep signing keys and state writes inside ``tmp_path``."""
    key_file = tmp_path / "hmac.key"
    key_file.write_bytes(b"0" * 32)
    with (
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
        patch(
            "wake_alarm._workday_penalty.WORKDAY_PENALTY_FILE",
            tmp_path / "workday_penalty.json",
        ),
        # The shared free-day pool lives under ~/.local/share, outside every
        # path above. Without this, a real free day on the developer's
        # machine would silence the alarm in every trigger test here.
        patch(
            "freedays._api.resolve_paths",
            lambda paths: paths or freedays.Paths.under(tmp_path / "freedays"),
        ),
    ):
        yield
