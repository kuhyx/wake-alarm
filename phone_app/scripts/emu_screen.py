"""Pixel-hunting on the emulator screen for ``emu_morning.py``.

Finds the check-in's submit button in ``screencap``'s raw RGBA dump by its
gold colour and taps relative to it: the weight field above it, the energy
chips above that. No image library. Split out of ``emu_morning.py`` to keep
both under the shared 250-line cap.
"""

from __future__ import annotations

import struct
import time

from emu_adb import adb

KEY_ENTER = "66"
KEY_DEL = "67"
KEY_CTRL_A = ("113", "29")
# The FilledButton's gold, as (min red, green range, max blue).
GOLD_RED_MIN = 170
GOLD_GREEN = (120, 170)
GOLD_BLUE_MAX = 90
# Columns sampled per row, and gold samples that make a row "button".
SAMPLE_STEP = 4
GOLD_HITS_MIN = 20
# The text field sits this fraction of the screen height above the button.
FIELD_ABOVE_BUTTON = 0.079
# The energy chip row sits above the field; chips are spread edge to edge
# inside the 24 dp page padding, so chip n's centre is a fixed fraction of
# the width. Both tuned on the Pixel 6a AVD like FIELD_ABOVE_BUTTON.
ENERGY_ABOVE_BUTTON = 0.135
ENERGY_CHIP_X = (0.10, 0.30, 0.50, 0.70, 0.90)


def raw_screen(serial: str) -> tuple[int, int, bytes]:
    """The screen as (width, height, RGBA bytes), from screencap's raw dump."""
    data = adb(serial, "exec-out", "screencap")
    width, height = struct.unpack("<II", data[:8])
    # Header is 12 bytes (w, h, format) or 16 (plus colour space) by API.
    header = len(data) - width * height * 4
    if header not in (12, 16):
        msg = f"unexpected screencap layout: {len(data)} bytes"
        raise SystemExit(msg)
    return width, height, data[header:]


def find_button_y(serial: str) -> tuple[int, int] | None:
    """(row, screen height) of the gold FilledButton, or None when absent."""
    width, height, pixels = raw_screen(serial)
    rows = []
    for y in range(height):
        hits = 0
        for x in range(0, width, SAMPLE_STEP):
            i = (y * width + x) * 4
            red, green, blue = pixels[i], pixels[i + 1], pixels[i + 2]
            if (
                red > GOLD_RED_MIN
                and GOLD_GREEN[0] < green < GOLD_GREEN[1]
                and blue < GOLD_BLUE_MAX
            ):
                hits += 1
        if hits > GOLD_HITS_MIN:
            rows.append(y)
    if not rows:
        return None
    return (rows[0] + rows[-1]) // 2, height


def focus_field(serial: str) -> bool:
    """Taps the text field sitting above the submit button."""
    found = find_button_y(serial)
    if found is None:
        return False
    y, height = found
    width = raw_screen(serial)[0]
    field_y = int(y - height * FIELD_ABOVE_BUTTON)
    adb(serial, "shell", "input", "tap", str(width // 2), str(field_y))
    time.sleep(1)
    return True


def tap_energy(serial: str, level: int) -> None:
    """Taps energy chip [level] (1-5) in the row above the weight field."""
    found = find_button_y(serial)
    if found is None:
        msg = "no submit button on screen"
        raise SystemExit(msg)
    y, height = found
    width = raw_screen(serial)[0]
    chip_x = int(width * ENERGY_CHIP_X[level - 1])
    chip_y = int(y - height * ENERGY_ABOVE_BUTTON)
    adb(serial, "shell", "input", "tap", str(chip_x), str(chip_y))
    time.sleep(1)


def type_and_submit(serial: str, text: str) -> None:
    """Focuses the field, replaces its content with [text], presses Enter."""
    if not focus_field(serial):
        msg = "no submit button on screen"
        raise SystemExit(msg)
    adb(serial, "shell", "input", "keycombination", *KEY_CTRL_A)
    adb(serial, "shell", "input", "keyevent", KEY_DEL)
    adb(serial, "shell", "input", "text", text)
    time.sleep(0.5)
    adb(serial, "shell", "input", "keyevent", KEY_ENTER)
    time.sleep(2)
