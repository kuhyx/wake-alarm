"""Shared fixtures keeping the wake_alarm suite off the real machine.

Since gatelock v0.2.0 the lock builds one real ``tk.Toplevel`` per live
output. Two consequences for tests, both of which bite silently:

* ``tk.Toplevel`` over a ``MagicMock`` master sends real tkinter into infinite
  mock recursion -- the run **hangs** rather than failing, which is far harder
  to diagnose than an error.
* An unpatched lock setup shells out to ``setxkbmap`` and really disables VT
  switching on the machine running the tests, and reaches the real
  ``$XDG_RUNTIME_DIR``, where it could stand a *production* locker down.

Sink reactivation adds a fourth: ``WakeAlarm.__init__`` starts a background
thread that really shells out to ``pactl set-card-profile`` and would reshape
the *host's* audio routing mid-test.

The power-key inhibitor and the session record add a fifth and a sixth: an
unstubbed run really spawns ``systemd-inhibit`` (blocking the machine's power
button for as long as the test process lives) and really writes the
*production* ``alarm_session.json``, which the next real trigger tick would
then act on. All three are stubbed here and re-patched explicitly by the tests
that assert the wiring.

The escape hatch adds a third: ``WakeAlarm.__init__`` builds its tracker over
the real ``ESCAPE_HISTORY_FILE``, so an unpatched run both reads a *production*
budget -- making "the button appears" tests fail on any day the real budget is
spent -- and could write to it.

So this is autouse and deliberately broad.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock import Output, OutputRect
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


FAKE_OUTPUTS = (
    Output(
        "VIRTUAL-1",
        connected=True,
        rect=OutputRect(0, 0, 1920, 1080),
        primary=True,
    ),
)
"""One live output, so the Tk-screen fallback (which would call int() on a
MagicMock) is never reached."""

TWO_OUTPUTS = (
    Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True),
    Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440)),
)
"""The real desk. Opt into it with the ``dual_output`` fixture for anything
asserting that work fans out: against ``FAKE_OUTPUTS`` a loop that only ever
touched the first surface would pass every assertion."""


def make_toplevel(_parent: object = None, **_kwargs: object) -> MagicMock:
    """A Toplevel stand-in that remembers the geometry it was given."""
    window = MagicMock()
    state = {"x": 0, "y": 0, "w": 0, "h": 0, "mapped": False}

    def geometry(spec: str) -> None:
        size, x, y = spec.split("+")
        width, height = size.split("x")
        state.update(x=int(x), y=int(y), w=int(width), h=int(height))

    window.geometry.side_effect = geometry
    window.deiconify.side_effect = lambda: state.update(mapped=True)
    window.withdraw.side_effect = lambda: state.update(mapped=False)
    window.winfo_ismapped.side_effect = lambda: state["mapped"]
    window.winfo_rootx.side_effect = lambda: state["x"]
    window.winfo_rooty.side_effect = lambda: state["y"]
    window.winfo_width.side_effect = lambda: state["w"]
    window.winfo_height.side_effect = lambda: state["h"]
    return window


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Block every path from the lock to the real display or machine."""
    monkeypatch.setenv("GATELOCK_RUNTIME_DIR", str(tmp_path / "gatelock-runtime"))
    key_file = tmp_path / "hmac.key"
    key_file.write_bytes(b"0" * 32)
    with (
        # The real key is root-owned but world-readable, so an unpatched run
        # signs test entries with the *production* key on this machine and
        # with none at all anywhere else. Pin it so the suite is portable.
        patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key_file),
        patch(
            "wake_alarm._escape_flow.ESCAPE_HISTORY_FILE",
            tmp_path / "escape_history.json",
        ),
        patch("wake_alarm._alarm.start_alarm_reactivation"),
        patch("wake_alarm._alarm.take_power_key_inhibitor", return_value=None),
        patch("wake_alarm._alarm.release_power_key_inhibitor"),
        patch("wake_alarm._alarm.start_session"),
        patch("wake_alarm._alarm.finish_session"),
        patch("gatelock._surfaces.tk.Toplevel", side_effect=make_toplevel),
        patch("gatelock._outputs.RandrBackend.create", return_value=None),
        patch("gatelock._outputs.scan_xrandr", return_value=FAKE_OUTPUTS),
        patch("gatelock._detect._RandrEventSource.start", return_value=False),
        patch("gatelock._vt.shutil.which", return_value="/usr/bin/setxkbmap"),
        patch("gatelock._vt.subprocess.run"),
    ):
        yield


@pytest.fixture
def dual_output(_hermetic: None) -> Generator[None]:
    """Re-scan as a two-monitor desk, layered over the single-output default.

    Depends on ``_hermetic`` so pytest is obliged to apply it second; the
    ``scan_xrandr`` patch here has to be the one that wins.
    """
    with patch("gatelock._outputs.scan_xrandr", return_value=TWO_OUTPUTS):
        yield
