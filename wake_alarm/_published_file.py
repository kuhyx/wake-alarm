"""A planted stand-in for ``fetch_firebase_logs()``: ``--published FILE``.

Only for ``_fallback --dry-run``: the live check of the bypass ring needs
``bypass`` / ``dismissed`` events the PC can read, and there is no test
backend to put them in. The file is a JSON list of ``[device_id, alarm]``
pairs, the shape ``fetch_firebase_logs()`` returns. ``alarm`` is the
decrypted ``alarm.json`` -- an object (re-serialised here) or its raw text,
passed through as-is.
"""

from __future__ import annotations

import json
from pathlib import Path

_PAIR_LEN = 2


def _pair(entry: object) -> tuple[str, str]:
    """One ``[device_id, alarm]`` entry as ``(device_id, raw_json)``."""
    if not isinstance(entry, list) or len(entry) != _PAIR_LEN:
        msg = f"expected [device_id, alarm], got {entry!r}"
        raise TypeError(msg)
    device, alarm = entry
    if not isinstance(device, str):
        msg = f"device id must be a string, got {device!r}"
        raise TypeError(msg)
    if isinstance(alarm, str):
        return device, alarm
    if isinstance(alarm, dict):
        return device, json.dumps(alarm)
    msg = f"alarm for {device!r} must be an object or its JSON text"
    raise TypeError(msg)


def load_published(path: str) -> list[tuple[str, str]]:
    """The planted logs; OSError/ValueError/TypeError when the file is unusable."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        msg = "expected a JSON list of [device_id, alarm] pairs"
        raise TypeError(msg)
    return [_pair(entry) for entry in raw]
