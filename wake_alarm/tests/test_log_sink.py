"""Tests for the JSONL log sink."""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING

from wake_alarm._log_sink import BACKUP_COUNT, MAX_BYTES, JsonlFormatter, build_handler

if TYPE_CHECKING:
    from pathlib import Path


def _record(msg: str = "hello", *, level: int = logging.INFO) -> logging.LogRecord:
    """Build a plain log record."""
    return logging.LogRecord("wake_alarm.t", level, __file__, 7, msg, None, None)


def test_format_emits_single_line_json() -> None:
    """One record renders as exactly one parseable JSON line."""
    rendered = JsonlFormatter().format(_record())
    assert "\n" not in rendered
    assert json.loads(rendered)["msg"] == "hello"


def test_format_includes_core_fields() -> None:
    """Level, logger and timestamp are always present."""
    payload = json.loads(JsonlFormatter().format(_record(level=logging.WARNING)))
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "wake_alarm.t"
    assert payload["ts"]


def test_format_interpolates_arguments() -> None:
    """``%s`` style arguments are rendered, not left raw."""
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hi %s", ("bob",), None)
    assert json.loads(JsonlFormatter().format(record))["msg"] == "hi bob"


def test_format_merges_extra_fields() -> None:
    """Caller supplied ``extra=`` keys become top-level payload fields."""
    record = _record()
    record.corr = "wake-20260826-0700"
    assert json.loads(JsonlFormatter().format(record))["corr"] == "wake-20260826-0700"


def test_format_skips_private_attributes() -> None:
    """Underscore-prefixed attributes stay out of the payload."""
    record = _record()
    record._hidden = "no"
    assert "_hidden" not in json.loads(JsonlFormatter().format(record))


def test_format_renders_unserialisable_values() -> None:
    """A value JSON cannot encode falls back to repr instead of raising."""
    record = _record()
    record.thing = object()
    assert "object" in json.loads(JsonlFormatter().format(record))["thing"]


def test_format_includes_exception_text() -> None:
    """An exc_info record carries the traceback under ``exc``."""

    def _raise() -> None:
        msg = "boom"
        raise ValueError(msg)

    try:
        _raise()
    except ValueError:
        record = logging.LogRecord(
            "t",
            logging.ERROR,
            __file__,
            1,
            "failed",
            None,
            sys.exc_info(),
        )
    assert "ValueError" in json.loads(JsonlFormatter().format(record))["exc"]


def test_build_handler_creates_parent_directory(tmp_path: Path) -> None:
    """The state directory is created on demand."""
    target = tmp_path / "deep" / "nested" / "events.jsonl"
    build_handler(target).close()
    assert target.parent.is_dir()


def test_build_handler_is_configured_for_rotation(tmp_path: Path) -> None:
    """Rotation bounds are applied so the log cannot grow without limit."""
    handler = build_handler(tmp_path / "e.jsonl")
    try:
        assert handler.maxBytes == MAX_BYTES
        assert handler.backupCount == BACKUP_COUNT
    finally:
        handler.close()


def test_handler_writes_a_parseable_line(tmp_path: Path) -> None:
    """End to end: emitting through the handler yields valid JSONL."""
    target = tmp_path / "e.jsonl"
    handler = build_handler(target)
    try:
        handler.emit(_record("written"))
    finally:
        handler.close()
    assert json.loads(target.read_text(encoding="utf-8").strip())["msg"] == "written"
