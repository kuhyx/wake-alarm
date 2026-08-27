"""Tests for the curtain driver the alarm calls on its wake sequence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from wake_alarm import _curtains
from wake_alarm._curtains import NoOpCurtains, get_driver, open_curtains

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the config at a temporary path, never the real one."""
    path = tmp_path / "curtains.json"
    monkeypatch.setattr(_curtains, "CURTAINS_CONFIG_FILE", path)
    return path


def _write(path: Path, payload: object) -> None:
    """Write *payload* as the curtain config."""
    path.write_text(json.dumps(payload))


class TestNoOpDriver:
    """The default driver on a machine with no curtain motor."""

    def test_open_reports_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logging the intent counts as success — there is nothing to fail."""
        with caplog.at_level("INFO"):
            assert NoOpCurtains().open() is True
        assert "would open" in caplog.text

    def test_close_reports_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """The close half exists so a driver swap has both ends to implement."""
        with caplog.at_level("INFO"):
            assert NoOpCurtains().close() is True
        assert "would close" in caplog.text


class TestDriverSelection:
    """Choosing a driver from config, and every way that can go wrong."""

    def test_no_config_means_the_noop(self) -> None:
        """The ordinary case today: no file, no hardware, no error."""
        assert isinstance(get_driver(), NoOpCurtains)

    def test_explicit_noop(self, config_file: Path) -> None:
        """Naming the default explicitly works too."""
        _write(config_file, {"driver": "noop"})
        assert isinstance(get_driver(), NoOpCurtains)

    def test_unknown_driver_falls_back(
        self, config_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A typo must not stop the alarm; it degrades and says so loudly."""
        _write(config_file, {"driver": "definitely-not-a-motor"})
        with caplog.at_level("WARNING"):
            assert isinstance(get_driver(), NoOpCurtains)
        assert "Unknown curtain driver" in caplog.text

    def test_non_string_driver_is_ignored(self, config_file: Path) -> None:
        """A JSON number where a name belongs is not a driver."""
        _write(config_file, {"driver": 42})
        assert isinstance(get_driver(), NoOpCurtains)

    def test_malformed_json_falls_back(
        self, config_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A half-written config means no curtains, not a crash."""
        config_file.write_text("{not json")
        with caplog.at_level("WARNING"):
            assert isinstance(get_driver(), NoOpCurtains)
        assert "Cannot read" in caplog.text

    def test_non_dict_config_falls_back(
        self, config_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A JSON list is not a config object."""
        _write(config_file, ["noop"])
        with caplog.at_level("WARNING"):
            assert isinstance(get_driver(), NoOpCurtains)
        assert "not a JSON object" in caplog.text


class TestOpenCurtains:
    """The entry point the alarm's startup path calls."""

    def test_opens_via_the_configured_driver(self) -> None:
        """The ordinary path."""
        assert open_curtains() is True

    def test_a_failing_driver_never_stops_the_alarm(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A jammed motor is a curtain problem, not an alarm problem.

        The call sits on the startup path, so an exception escaping here would
        take the whole alarm down and the user would not be woken at all.
        """

        class Jammed:
            def open(self) -> bool:
                msg = "the motor is stuck"
                raise RuntimeError(msg)

            def close(self) -> bool:
                return False

        monkeypatch.setattr(_curtains, "get_driver", Jammed)
        with caplog.at_level("WARNING"):
            assert open_curtains() is False
        assert "the alarm continues" in caplog.text
