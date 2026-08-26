"""Tests for the no-real-sink warning."""

from __future__ import annotations

from unittest.mock import patch

from wake_alarm._sinks import (
    _warn_if_no_real_sink,
)

# A representative `pactl list cards` block covering every parse branch:
# an HDMI card (off, with an available stereo output profile), an input-only
# card (no output profile), a card block with no Name line (must be skipped).
_CARDS_TEXT = """Card #54
\tName: alsa_card.hdmi
\tDriver: module-alsa-card.c
\tProfiles:
\t\toff: Off (sinks: 0, sources: 0, priority: 0, available: yes)
\t\toutput:hdmi-stereo: Stereo (sinks: 1, priority: 5900, available: yes)
\t\toutput:hdmi-surround: Surround (sinks: 1, priority: 600, available: no)
\t\tbroken (available: yes)
\tActive Profile: off
Card #55
\tName: alsa_card.mic
\tProfiles:
\t\toff: Off (sinks: 0, sources: 0, priority: 0, available: yes)
\tActive Profile: off
Card #56
\tProfiles:
\t\toutput:noname: NoName (available: yes)
\tActive Profile: off
"""

# A `pactl list sinks` block: a normal sink, plus one whose Volume line has
# no integer (to cover the "no digit" branch), plus a leading non-Name line.
_SINKS_TEXT = """Sink #62
\tState: SUSPENDED
\tName: alsa_output.analog
\tMute: no
\tVolume: front-left: 65536 / 100%
\tDescription: Built-in Analog
Sink #63
\tName: alsa_output.weird
\tMute: yes
\tVolume: n/a
"""


class TestWarnIfNoRealSink:
    """Tests for _warn_if_no_real_sink."""

    def test_logs_when_pactl_missing(self) -> None:
        """No pactl on PATH → warns and returns (no sink lookup)."""
        with (
            patch("wake_alarm._sinks._pactl_path", return_value=None),
            patch("wake_alarm._sinks._list_real_sinks") as mock_list,
        ):
            _warn_if_no_real_sink()
            mock_list.assert_not_called()

    def test_warns_when_no_real_sink(self) -> None:
        """No real sink → warning is emitted."""
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._sinks._list_real_sinks", return_value=[]),
            patch("wake_alarm._sinks._logger") as mock_log,
        ):
            _warn_if_no_real_sink()
            mock_log.warning.assert_called()

    def test_info_when_real_sink_present(self) -> None:
        """A real sink → info log, no warning."""
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch(
                "wake_alarm._sinks._list_real_sinks",
                return_value=["alsa_output.analog"],
            ),
            patch("wake_alarm._sinks._logger") as mock_log,
        ):
            _warn_if_no_real_sink()
            mock_log.info.assert_called()
            mock_log.warning.assert_not_called()
