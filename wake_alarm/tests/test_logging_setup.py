"""Tests for wiring the journal and JSONL sinks together."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from wake_alarm import _logging_setup
from wake_alarm._logging_setup import configure_logging

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the sink at a temp dir and restore root handlers afterwards.

    Without this a test would attach a real handler to the process-wide root
    logger and write into the developer's own state directory.
    """
    monkeypatch.setattr(_logging_setup, "LOG_JSONL_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(_logging_setup, "LOG_DEDUPE_FILE", tmp_path / "last.json")
    root = logging.getLogger()
    original = list(root.handlers)
    # pytest's logging plugin pins the root level; basicConfig() cannot lower
    # it once handlers exist, so INFO records would be filtered before reaching
    # our sink. Force it, and restore afterwards.
    original_level = root.level
    root.setLevel(logging.INFO)
    # Another module's test may already have installed our handler on the
    # process-wide root logger, which would make configure_logging() a no-op
    # here. Detach any such handler so each test starts from a clean root.
    stashed = [h for h in original if getattr(h, "_wake_alarm_jsonl", False)]
    for handler in stashed:
        root.removeHandler(handler)
    yield tmp_path
    root.setLevel(original_level)
    for handler in stashed:
        root.addHandler(handler)
    for handler in list(root.handlers):
        if handler not in original:
            handler.close()
            root.removeHandler(handler)


def _flush() -> None:
    """Flush root handlers so the JSONL file reflects what was emitted."""
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_configure_attaches_the_jsonl_handler() -> None:
    """A structured handler is installed alongside the stderr one."""
    before = len(logging.getLogger().handlers)
    configure_logging(component="alarm")
    assert len(logging.getLogger().handlers) > before


def test_records_reach_the_jsonl_file(log_dir: Path) -> None:
    """An ordinary log call lands in the structured file."""
    configure_logging(component="alarm")
    logging.getLogger("wake_alarm.t").warning("ALARM TRIGGERED")
    _flush()
    written = (log_dir / "events.jsonl").read_text(encoding="utf-8")
    assert json.loads(written.strip())["msg"] == "ALARM TRIGGERED"


def test_component_is_stamped_on_every_record(log_dir: Path) -> None:
    """Records identify which entry point produced them."""
    configure_logging(component="trigger")
    logging.getLogger("wake_alarm.t").info("tick")
    _flush()
    payload = json.loads((log_dir / "events.jsonl").read_text().strip())
    assert payload["component"] == "trigger"


def test_second_call_does_not_duplicate_the_handler() -> None:
    """Re-entry (``--demo``, tests) must not double every line."""
    configure_logging(component="alarm")
    count = len(logging.getLogger().handlers)
    configure_logging(component="alarm")
    assert len(logging.getLogger().handlers) == count


def test_dedupe_filter_is_active(log_dir: Path) -> None:
    """Consecutive identical routine events collapse to one line."""
    configure_logging(component="trigger")
    log = logging.getLogger("wake_alarm.t")
    for _ in range(4):
        log.info("idle", extra={"dedupe_key": "idle"})
    _flush()
    lines = (log_dir / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1


def test_unwritable_destination_degrades_to_journal_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing sink must not stop the alarm from running."""

    def _boom(_path: Path) -> None:
        msg = "read-only"
        raise OSError(msg)

    monkeypatch.setattr(_logging_setup, "build_handler", _boom)
    before = len(logging.getLogger().handlers)
    configure_logging(component="alarm")
    assert len(logging.getLogger().handlers) == before
