"""How the PC goes down for the night: ``hibernate`` (default) or ``poweroff``.

``~/.config/wake_alarm/pc_wake.json`` ``{"mode": "hibernate" | "poweroff"}``.
In ``hibernate`` mode ``install.sh`` installs a logind drop-in that makes the
power key hibernate -- verified on this host to resume from the RTC alarm.
``poweroff`` relies on the firmware waking from S5 and changes nothing.

Anything missing or unreadable is ``hibernate``: the verified path.

    python -m wake_alarm._pc_wake_mode   # prints the mode (install.sh reads it)
"""

from __future__ import annotations

import json
import logging
import sys

from wake_alarm._constants import PC_WAKE_CONFIG

_logger = logging.getLogger(__name__)

HIBERNATE = "hibernate"
POWEROFF = "poweroff"
MODES = frozenset({HIBERNATE, POWEROFF})


def read_mode() -> str:
    """The configured mode, ``hibernate`` unless the file says otherwise."""
    try:
        raw = json.loads(PC_WAKE_CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HIBERNATE
    except (OSError, ValueError) as exc:
        _logger.warning("Unreadable %s (%s); using hibernate", PC_WAKE_CONFIG, exc)
        return HIBERNATE
    mode = raw.get("mode") if isinstance(raw, dict) else None
    if mode not in MODES:
        _logger.warning("Unknown mode %r in %s; using hibernate", mode, PC_WAKE_CONFIG)
        return HIBERNATE
    return str(mode)


def main() -> int:
    """Print the mode."""
    sys.stdout.write(f"{read_mode()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
