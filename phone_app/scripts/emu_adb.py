"""The one adb call the emulator drivers share."""

from __future__ import annotations

import shutil
import subprocess

ADB = shutil.which("adb") or "/usr/bin/adb"


def adb(serial: str, *args: str) -> bytes:
    """Runs one adb command and returns its raw stdout."""
    return subprocess.run(
        [ADB, "-s", serial, *args], capture_output=True, check=False
    ).stdout


def adb_text(serial: str, *args: str) -> str:
    """Runs one adb command and returns its stdout as text."""
    return adb(serial, *args).decode(errors="replace")
