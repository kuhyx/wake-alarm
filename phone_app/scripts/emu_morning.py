#!/usr/bin/env python3
"""Drive the whole morning on the emulator over adb.

Companion to ``lib/main_session_probe.dart``: that entrypoint replaces the
phone's NFC and step sensor with files, and this script writes those files
and types the challenge answers it reads back from logcat. Everything else
(the ring service, the re-ring alarms, the session clocks) is the real code.

    scripts/emu_morning.py dismiss          # tag 1, walk, tag 2, 3 answers
    scripts/emu_morning.py tag bath         # one session tag
    scripts/emu_morning.py idle 300000      # the phone "lay still" 5 min
    scripts/emu_morning.py weight 72.4      # type a weight and submit
    scripts/emu_morning.py shot out.png     # screenshot

Reads answers from a ``flutter run`` log (``--log``) or from ``adb logcat``.
No image library: the submit button is found in ``screencap``'s raw RGBA
dump by its gold colour.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

PACKAGE = "com.kuhy.wake_alarm_sync"
FILES = f"/sdcard/Android/data/{PACKAGE}/files"
KEY_ENTER = "66"
KEY_DEL = "67"
KEY_CTRL_A = ("113", "29")
ANSWER_RE = re.compile(r"answer=(\S+)")
# The FilledButton's gold, as (min red, green range, max blue).
GOLD_RED_MIN = 170
GOLD_GREEN = (120, 170)
GOLD_BLUE_MAX = 90
# Columns sampled per row, and gold samples that make a row "button".
SAMPLE_STEP = 4
GOLD_HITS_MIN = 20
# The text field sits this fraction of the screen height above the button.
FIELD_ABOVE_BUTTON = 0.079
ADB = shutil.which("adb") or "/usr/bin/adb"


def adb(serial: str, *args: str) -> bytes:
    """Runs one adb command and returns its raw stdout."""
    return subprocess.run(
        [ADB, "-s", serial, *args], capture_output=True, check=False
    ).stdout


def adb_text(serial: str, *args: str) -> str:
    """Runs one adb command and returns its stdout as text."""
    return adb(serial, *args).decode(errors="replace")


def write_file(serial: str, name: str, content: str) -> None:
    """Writes one harness input file on the device."""
    adb(serial, "shell", f"mkdir -p {FILES} && printf %s '{content}' > {FILES}/{name}")


def screenshot(serial: str, path: Path) -> None:
    """Captures the screen as PNG to [path]."""
    path.write_bytes(adb(serial, "exec-out", "screencap", "-p"))


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


def log_text(serial: str, log: Path | None) -> str:
    """The flutter run log, or the device's flutter logcat."""
    return log.read_text() if log else adb_text(serial, "logcat", "-d", "-s", "flutter")


def last_answer(serial: str, log: Path | None) -> str | None:
    """The newest challenge answer the ring logged."""
    found = ANSWER_RE.findall(log_text(serial, log))
    return found[-1] if found else None


def session_started(serial: str, log: Path | None) -> bool:
    """Whether the session screen has logged its start since the last ring."""
    text = log_text(serial, log)
    return text.rfind("WakeAlarmSession: started") > text.rfind("challenge kind=")


def dismiss(serial: str, log: Path | None) -> None:
    """Tag 1, thirty steps, tag 2, then answers until the session starts."""
    write_file(serial, "steps", "30")
    write_file(serial, "tag", "ring1")
    time.sleep(4)
    write_file(serial, "tag", "ring2")
    time.sleep(3)
    for _ in range(8):
        answer = last_answer(serial, log)
        if answer is None:
            msg = "no challenge logged yet"
            raise SystemExit(msg)
        type_and_submit(serial, answer)
        if session_started(serial, log):
            return
    msg = "still ringing after eight answers"
    raise SystemExit(msg)


def main(argv: list[str]) -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--log", type=Path, help="flutter run log to read answers from")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dismiss")
    sub.add_parser("tag").add_argument("id")
    sub.add_parser("idle").add_argument("ms")
    sub.add_parser("weight").add_argument("kg")
    sub.add_parser("shot").add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "dismiss":
        dismiss(args.serial, args.log)
    elif args.cmd == "tag":
        write_file(args.serial, "tag", args.id)
    elif args.cmd == "idle":
        write_file(args.serial, "idle_ms", args.ms)
    elif args.cmd == "weight":
        type_and_submit(args.serial, args.kg)
    elif args.cmd == "shot":
        screenshot(args.serial, args.path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
