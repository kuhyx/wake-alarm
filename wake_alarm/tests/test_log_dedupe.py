"""Tests for cross-process consecutive-event suppression."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from wake_alarm._log_dedupe import REPEATS_FIELD, DedupeFilter

if TYPE_CHECKING:
    from pathlib import Path


def _record(
    msg: str, *, key: str | None = None, level: int = logging.INFO
) -> logging.LogRecord:
    """Build a log record, optionally carrying a dedupe key."""
    record = logging.LogRecord("t", level, __file__, 1, msg, None, None)
    if key is not None:
        record.dedupe_key = key
    return record


def test_record_without_key_always_passes(tmp_path: Path) -> None:
    """Only records that opt in are ever suppressed."""
    dedupe = DedupeFilter(tmp_path / "s.json")
    assert dedupe.filter(_record("a")) is True
    assert dedupe.filter(_record("a")) is True


def test_non_string_key_passes(tmp_path: Path) -> None:
    """A malformed key is ignored rather than crashing the logger."""
    dedupe = DedupeFilter(tmp_path / "s.json")
    record = _record("a")
    record.dedupe_key = 42
    assert dedupe.filter(record) is True


def test_first_record_passes_and_duplicate_is_suppressed(tmp_path: Path) -> None:
    """The first of a run is emitted; the rest are dropped."""
    dedupe = DedupeFilter(tmp_path / "s.json")
    assert dedupe.filter(_record("a", key="idle")) is True
    assert dedupe.filter(_record("a", key="idle")) is False


def test_distinct_key_passes_and_carries_the_count(tmp_path: Path) -> None:
    """Breaking a run surfaces how many duplicates were suppressed."""
    dedupe = DedupeFilter(tmp_path / "s.json")
    dedupe.filter(_record("a", key="idle"))
    for _ in range(3):
        dedupe.filter(_record("a", key="idle"))
    record = _record("b", key="fired")
    assert dedupe.filter(record) is True
    assert getattr(record, REPEATS_FIELD) == 3


def test_no_count_attached_when_nothing_was_suppressed(tmp_path: Path) -> None:
    """A clean transition does not add a zero-valued field."""
    dedupe = DedupeFilter(tmp_path / "s.json")
    dedupe.filter(_record("a", key="one"))
    record = _record("b", key="two")
    assert dedupe.filter(record) is True
    assert not hasattr(record, REPEATS_FIELD)


def test_same_key_at_a_different_level_is_not_a_duplicate(tmp_path: Path) -> None:
    """Level is part of the fingerprint: an escalation must not be swallowed."""
    dedupe = DedupeFilter(tmp_path / "s.json")
    assert dedupe.filter(_record("a", key="k")) is True
    assert dedupe.filter(_record("a", key="k", level=logging.WARNING)) is True


def test_state_persists_across_filter_instances(tmp_path: Path) -> None:
    """A fresh process (new filter, same file) still suppresses the duplicate."""
    state = tmp_path / "s.json"
    assert DedupeFilter(state).filter(_record("a", key="idle")) is True
    assert DedupeFilter(state).filter(_record("a", key="idle")) is False


@pytest.mark.parametrize(
    "payload", ["not json", '"a string"', '{"digest": 1}', '{"count": "x"}']
)
def test_corrupt_state_is_treated_as_empty(tmp_path: Path, payload: str) -> None:
    """A damaged state file must not suppress a record or raise."""
    state = tmp_path / "s.json"
    state.write_text(payload, encoding="utf-8")
    assert DedupeFilter(state).filter(_record("a", key="idle")) is True


def test_missing_state_file_is_treated_as_empty(tmp_path: Path) -> None:
    """A first-ever run has no state file and must still emit."""
    assert DedupeFilter(tmp_path / "absent.json").filter(_record("a", key="k")) is True


def test_unwritable_state_does_not_raise(tmp_path: Path) -> None:
    """Logging must never be the thing that breaks the alarm."""
    state = tmp_path / "sub" / "s.json"
    state.parent.mkdir()
    state.parent.chmod(0o500)
    try:
        assert DedupeFilter(state).filter(_record("a", key="k")) is True
    finally:
        state.parent.chmod(0o700)


def test_state_file_records_the_digest_and_count(tmp_path: Path) -> None:
    """The persisted shape is what a later process expects to read."""
    state = tmp_path / "s.json"
    dedupe = DedupeFilter(state)
    dedupe.filter(_record("a", key="idle"))
    dedupe.filter(_record("a", key="idle"))
    stored = json.loads(state.read_text(encoding="utf-8"))
    assert stored["count"] == 1
    assert isinstance(stored["digest"], str)
