#!/usr/bin/env python3
"""Drive the whole morning on the emulator over adb.

Companion to ``lib/main_session_probe.dart``: that entrypoint replaces the
phone's NFC and step sensor with files, and this script writes those files
and types the challenge answers it reads back from logcat. Everything else
(the ring service, the re-ring alarms, the session clocks) is the real code.

    scripts/emu_morning.py dismiss          # tag 1, walk, tag 2, 3 answers
    scripts/emu_morning.py tag bath         # one session tag
    scripts/emu_morning.py rering           # fire the deadline alarm now
    scripts/emu_morning.py energy 3         # tap energy chip 1-5
    scripts/emu_morning.py weight 72.4      # type a weight and submit
    scripts/emu_morning.py home             # leave the app (home gesture)
    scripts/emu_morning.py launch           # tap the launcher icon
    scripts/emu_morning.py shot out.png     # screenshot

Reads answers from a ``flutter run`` log (``--log``) or from ``adb logcat``.
No image library: the submit button is found in ``screencap``'s raw RGBA
dump by its gold colour.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import time

from emu_adb import adb, adb_text
from emu_screen import tap_energy, type_and_submit

PACKAGE = "com.kuhy.wake_alarm_sync"
FILES = f"/sdcard/Android/data/{PACKAGE}/files"
ANSWER_RE = re.compile(r"answer=(\S+)")


def write_file(serial: str, name: str, content: str) -> None:
    """Writes one harness input file on the device."""
    adb(serial, "shell", f"mkdir -p {FILES} && printf %s '{content}' > {FILES}/{name}")


def rering(serial: str) -> None:
    """Delivers the session-deadline broadcast, as AlarmManager would.

    Targets the receiver by component, so there is no waiting for a real
    ten-minute window. The receiver is not exported, so the shell user's
    broadcast is silently dropped (``result=0`` and nothing happens); adbd
    has to run as root, which a Google-APIs AVD allows and a Play one does
    not. Idempotent, so it is done here rather than left to the caller.
    """
    adb(serial, "root")
    adb(serial, "wait-for-device")
    adb(
        serial,
        "shell",
        "am broadcast -n",
        f"{PACKAGE}/.AlarmReceiver",
        "--es reason rering",
    )


def home(serial: str) -> None:
    """Backgrounds whatever is in front, as the home gesture does."""
    adb(serial, "shell", "input keyevent HOME")


def launch(serial: str) -> None:
    """Starts the app from its launcher entry, as a tap on the icon does."""
    adb(
        serial,
        "shell",
        "monkey -p",
        PACKAGE,
        "-c android.intent.category.LAUNCHER 1",
    )


def screenshot(serial: str, path: Path) -> None:
    """Captures the screen as PNG to [path]."""
    path.write_bytes(adb(serial, "exec-out", "screencap", "-p"))


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
    sub.add_parser("rering")
    sub.add_parser("home")
    sub.add_parser("launch")
    sub.add_parser("weight").add_argument("kg")
    sub.add_parser("energy").add_argument("level", type=int, choices=range(1, 6))
    sub.add_parser("shot").add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "dismiss":
        dismiss(args.serial, args.log)
    elif args.cmd == "tag":
        write_file(args.serial, "tag", args.id)
    elif args.cmd == "rering":
        rering(args.serial)
    elif args.cmd == "home":
        home(args.serial)
    elif args.cmd == "launch":
        launch(args.serial)
    elif args.cmd == "weight":
        type_and_submit(args.serial, args.kg)
    elif args.cmd == "energy":
        tap_energy(args.serial, args.level)
    elif args.cmd == "shot":
        screenshot(args.serial, args.path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
