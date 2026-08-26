"""Tests for the PC-speaker fallback beep."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from wake_alarm._audio import (
    _beep_pcspkr,
)


class TestBeepPcspkr:
    """Tests for _beep_pcspkr (evdev PC speaker)."""

    def test_writes_tone_then_zero_to_device(self) -> None:
        """Successful path writes start-frequency then stop event."""

        mock_dev = MagicMock()
        mock_open_ctx = MagicMock()
        mock_open_ctx.__enter__.return_value = mock_dev
        mock_open_ctx.__exit__.return_value = False
        with (
            patch(
                "wake_alarm._tone.Path.open",
                return_value=mock_open_ctx,
            ),
            patch("wake_alarm._audio.time.sleep"),
        ):
            _beep_pcspkr(1000, 0.05)
        # First write carries the frequency, second write carries 0 (stop).
        assert mock_dev.write.call_count == 2

    def test_oserror_is_swallowed(self) -> None:
        """OSError opening the device must not raise."""

        with patch(
            "wake_alarm._tone.Path.open",
            side_effect=OSError("no device"),
        ):
            _beep_pcspkr(1000, 0.05)  # must not raise
