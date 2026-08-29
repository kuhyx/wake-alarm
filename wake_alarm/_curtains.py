"""Open the curtains when the alarm fires, if any hardware is configured.

Item 5. There is **no curtain hardware yet**, so the default driver is a
logging no-op: it records what it would have done and returns. That is the
whole point of shipping this now rather than waiting for a motor — the alarm
sequence gains its call site, the JSONL log gains its event, and buying
hardware later is a config file, not a code change.

Deliberately shaped like :mod:`wake_alarm._smart_plug`, which solves the same
problem (optional hardware that must never delay or break the alarm):

* absent or malformed config means "no curtains", never an error;
* every failure is caught and logged, because a stuck motor must not stop the
  alarm from ringing;
* a driver's dependency is import-guarded, so an uninstalled library degrades
  to the no-op instead of killing the alarm process.

Config lives at ``~/.config/wake_alarm/curtains.json``::

    {"driver": "noop"}

``DOCS-curtains-hardware.md`` has the buy list and what each driver needs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

# Kept here rather than in _constants.py because this module is their only
# consumer -- the same call the repo already makes for _rounds.py's timing
# constants and _alarm_session.py's state names.
CURTAINS_CONFIG_FILE = Path.home() / ".config" / "wake_alarm" / "curtains.json"
"""Which motor to drive, if any. Absent => the no-op driver."""

CURTAINS_DEFAULT_DRIVER = "noop"
"""Used when nothing is configured, and when a config names an unknown one."""


class CurtainDriver(Protocol):
    """What any curtain implementation has to provide.

    Two methods, both of which must return rather than raise: the alarm calls
    them on its startup path, and a driver that throws would take the whole
    alarm down with it.
    """

    def open(self) -> bool:
        """Open the curtains. Returns True when the hardware acknowledged."""

    def close(self) -> bool:
        """Close the curtains. Returns True when the hardware acknowledged."""


class NoOpCurtains:
    """The default: log the intent, touch nothing.

    Not a placeholder to be replaced later so much as the correct behaviour on
    a machine with no curtain motor. It keeps the call site and the log event
    real, so the day hardware arrives the only change is a config file.
    """

    name = "noop"

    def open(self) -> bool:
        """Record that the curtains would have opened."""
        _logger.info(
            "Curtains: would open now (no hardware configured)",
            extra={"event": "curtains_open", "driver": self.name, "real": False},
        )
        return True

    def close(self) -> bool:
        """Record that the curtains would have closed."""
        _logger.info(
            "Curtains: would close now (no hardware configured)",
            extra={"event": "curtains_close", "driver": self.name, "real": False},
        )
        return True


# Driver registry. A new motor means adding one entry and one class, with its
# dependency import-guarded inside the factory so an uninstalled library
# degrades to the no-op rather than killing the alarm.
_DRIVERS: dict[str, Callable[[], CurtainDriver]] = {
    NoOpCurtains.name: NoOpCurtains,
}


def _load_config() -> dict[str, object] | None:
    """Return the curtain config, or None when there is none to read.

    Returns:
        The parsed config dict, or None when the file is absent, unreadable,
        or not a JSON object. Every one of those means "no curtains", which is
        the correct state on a machine that has none.
    """
    if not CURTAINS_CONFIG_FILE.exists():
        return None
    try:
        with CURTAINS_CONFIG_FILE.open() as handle:
            config = json.load(handle)
    except OSError, json.JSONDecodeError:
        _logger.warning(
            "Cannot read %s; falling back to the no-op curtain driver",
            CURTAINS_CONFIG_FILE,
        )
        return None
    if not isinstance(config, dict):
        _logger.warning("Curtain config is not a JSON object; using the no-op driver")
        return None
    return config


def get_driver() -> CurtainDriver:
    """Build the configured curtain driver, or the no-op when none applies.

    Returns:
        A driver honouring :class:`CurtainDriver`. Never None and never
        raising: the alarm calls this on its startup path.
    """
    config = _load_config()
    name = CURTAINS_DEFAULT_DRIVER
    if config is not None:
        requested = config.get("driver")
        if isinstance(requested, str):
            name = requested
    factory = _DRIVERS.get(name)
    if factory is None:
        _logger.warning(
            "Unknown curtain driver %r; using %s. Known drivers: %s",
            name,
            CURTAINS_DEFAULT_DRIVER,
            ", ".join(sorted(_DRIVERS)),
        )
        factory = _DRIVERS[CURTAINS_DEFAULT_DRIVER]
    return factory()


def open_curtains() -> bool:
    """Open the curtains as part of the alarm's wake sequence.

    Sunlight is the one wake cue that keeps working after the sound stops at
    ``FAILSAFE_SILENCE_SECONDS``, which is why this is worth a call site even
    with no motor attached yet.

    Returns:
        True when a driver reported success. A failure is logged and
        swallowed — a jammed curtain must never stop the alarm ringing.
    """
    try:
        return get_driver().open()
    except OSError, RuntimeError, ValueError:
        _logger.warning(
            "Curtain driver failed to open; the alarm continues",
            exc_info=True,
            extra={"event": "curtains_failed"},
        )
        return False
