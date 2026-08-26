"""Tests for forcing every card's output profile on."""

from __future__ import annotations

from unittest.mock import patch

from wake_alarm._constants import ALARM_AUDIO_SINK
from wake_alarm._sinks import (
    _activate_all_outputs,
    _AudioState,
    _CardInfo,
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


class TestActivateAllOutputs:
    """Tests for _activate_all_outputs."""

    def test_returns_none_when_pactl_missing(self) -> None:
        """No pactl on PATH → returns None without touching audio."""
        with (
            patch("wake_alarm._sinks._pactl_path", return_value=None),
            patch("wake_alarm._sinks.subprocess.run") as mock_run,
        ):
            assert _activate_all_outputs() is None
            mock_run.assert_not_called()

    def _sentinel_state(self) -> _AudioState:
        return _AudioState(
            default_sink="old",
            card_profiles={},
            sink_volumes={},
            sink_mutes={},
        )

    def test_activates_and_prefers_alarm_sink(self) -> None:
        """Forces card profiles on, maxes sinks, defaults to ALARM_AUDIO_SINK."""
        state = self._sentinel_state()
        cards = {
            "card_hdmi": _CardInfo(None, ["output:hdmi-stereo"]),
            "card_mic": _CardInfo(None, []),
        }
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._sinks._capture_audio_state", return_value=state),
            patch("wake_alarm._sinks._pactl_text", return_value=""),
            patch("wake_alarm._sinks._parse_cards", return_value=cards),
            patch(
                "wake_alarm._sinks._list_real_sinks",
                return_value=[ALARM_AUDIO_SINK, "other"],
            ),
            patch("wake_alarm._sinks._ensure_sink_audible") as mock_audible,
            patch("wake_alarm._sinks.subprocess.run") as mock_run,
        ):
            assert _activate_all_outputs() is state
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert [
            "/usr/bin/pactl",
            "set-card-profile",
            "card_hdmi",
            "output:hdmi-stereo",
        ] in cmds
        # The input-only card (no output profile) is never switched.
        assert not any(c[2] == "card_mic" for c in cmds if c[1] == "set-card-profile")
        assert ["/usr/bin/pactl", "set-default-sink", ALARM_AUDIO_SINK] in cmds
        assert mock_audible.call_count == 2

    def test_does_not_block_on_sink_enumeration(self) -> None:
        """Activation checks present sinks once — no polling/sleeping loop.

        The per-cycle presence check in _play_on_all_sinks is what covers a
        slow monitor sink, so activation must not spin waiting for it.
        """
        state = self._sentinel_state()
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._sinks._capture_audio_state", return_value=state),
            patch("wake_alarm._sinks._pactl_text", return_value=""),
            patch("wake_alarm._sinks._parse_cards", return_value={}),
            patch(
                "wake_alarm._sinks._list_real_sinks",
                return_value=[ALARM_AUDIO_SINK],
            ) as mock_list,
            patch("wake_alarm._sinks._ensure_sink_audible"),
            patch("wake_alarm._sinks.subprocess.run"),
        ):
            assert _activate_all_outputs() is state
        # Enumerated exactly once — no retry/poll loop.
        mock_list.assert_called_once()

    def test_falls_back_to_first_sink_when_alarm_sink_absent(self) -> None:
        """ALARM_AUDIO_SINK not present → default is the first present sink."""
        state = self._sentinel_state()
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._sinks._capture_audio_state", return_value=state),
            patch("wake_alarm._sinks._pactl_text", return_value=""),
            patch("wake_alarm._sinks._parse_cards", return_value={}),
            patch("wake_alarm._sinks._list_real_sinks", return_value=["other"]),
            patch("wake_alarm._sinks._ensure_sink_audible"),
            patch("wake_alarm._sinks.subprocess.run") as mock_run,
        ):
            assert _activate_all_outputs() is state
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert ["/usr/bin/pactl", "set-default-sink", "other"] in cmds

    def test_returns_state_when_no_sink_present(self) -> None:
        """No real sink present yet → returns state, no default, no maxing."""
        state = self._sentinel_state()
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._sinks._capture_audio_state", return_value=state),
            patch("wake_alarm._sinks._pactl_text", return_value=""),
            patch("wake_alarm._sinks._parse_cards", return_value={}),
            patch("wake_alarm._sinks._list_real_sinks", return_value=[]),
            patch("wake_alarm._sinks._ensure_sink_audible") as mock_audible,
            patch("wake_alarm._sinks.subprocess.run") as mock_run,
        ):
            assert _activate_all_outputs() is state
        mock_audible.assert_not_called()
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert not any(c[1] == "set-default-sink" for c in cmds)
