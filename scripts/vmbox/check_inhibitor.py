"""Guest-side check: does the power-key inhibitor register with logind?

Run by ``guest_cases.sh`` inside a vmbox sandbox. Prints a single line the
shell case compares exactly, so the harness adjudicates on a string rather
than on a human reading a log.

**What this proves and what it does not.** The guest has no physical power
button, so this shows the inhibitor is *taken* and *released* -- not that a
real press was suppressed. That distinction is stated in ``DOCS-vmbox.md``
rather than papered over.

The guest's polkit also refuses an inhibit from a non-interactive ssh session,
so ``REFUSED`` is an expected and passing outcome. It is what caught the real
bug: ``Popen`` succeeded while ``systemd-inhibit`` had already exited 1, and
the alarm logged the power key as blocked when it was not.
"""

from __future__ import annotations

import subprocess
import sys
import time

from wake_alarm._inhibit import (
    release_power_key_inhibitor,
    take_power_key_inhibitor,
)

_SETTLE_SECONDS = 1.0

# Absolute, so the check cannot be pointed at a different binary by PATH --
# and so it matches how _inhibit.py resolves the tool it actually spawns.
_SYSTEMD_INHIBIT = "/usr/bin/systemd-inhibit"


def _inhibitor_list() -> str:
    """Return logind's current inhibitor table as text."""
    return subprocess.run(
        [_SYSTEMD_INHIBIT, "--list"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def main() -> None:
    """Take the inhibitor, observe it, release it, observe it gone.

    Writes ``REFUSED`` when logind declined, which the harness treats as a
    *pass*: the point of the case is that the code never claims a block it did
    not get.
    """
    process = take_power_key_inhibitor()
    if process is None:
        sys.stdout.write("REFUSED\n")
        return

    time.sleep(_SETTLE_SECONDS)
    while_held = _inhibitor_list()
    release_power_key_inhibitor(process)
    time.sleep(_SETTLE_SECONDS)
    after_release = _inhibitor_list()

    held = "handle-power-key" in while_held and "wake-alarm" in while_held
    freed = "wake-alarm" not in after_release
    sys.stdout.write(
        f"{'HELD' if held else 'NOT-HELD'} {'FREED' if freed else 'NOT-FREED'}\n"
    )


if __name__ == "__main__":
    main()
