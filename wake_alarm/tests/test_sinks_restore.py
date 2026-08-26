"""Tests for restoring the audio state captured at alarm start."""

from __future__ import annotations

from unittest.mock import patch

from wake_alarm._sinks import (
    _AudioState,
    _restore_audio_state,
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


class TestRestoreAudioState:
    """Tests for _restore_audio_state."""

    def test_none_is_noop(self) -> None:
        """None state → does nothing, no pactl lookup."""
        with patch("wake_alarm._sinks._pactl_path") as mock_path:
            _restore_audio_state(None)
            mock_path.assert_not_called()

    def test_no_pactl_returns_silently(self) -> None:
        """State present but pactl missing → no raise, no run."""
        state = _AudioState(
            default_sink="s",
            card_profiles={},
            sink_volumes={},
            sink_mutes={},
        )
        with (
            patch("wake_alarm._sinks._pactl_path", return_value=None),
            patch("wake_alarm._sinks.subprocess.run") as mock_run,
        ):
            _restore_audio_state(state)
            mock_run.assert_not_called()

    def test_restores_everything(self) -> None:
        """Restores card profiles, sink volumes, mutes, and the default sink."""
        state = _AudioState(
            default_sink="analog",
            card_profiles={"card_hdmi": "off"},
            sink_volumes={"analog": "65536"},
            sink_mutes={"analog": True},
        )
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._sinks.subprocess.run") as mock_run,
        ):
            _restore_audio_state(state)
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert ["/usr/bin/pactl", "set-card-profile", "card_hdmi", "off"] in cmds
        assert ["/usr/bin/pactl", "set-sink-volume", "analog", "65536"] in cmds
        assert ["/usr/bin/pactl", "set-sink-mute", "analog", "1"] in cmds
        assert ["/usr/bin/pactl", "set-default-sink", "analog"] in cmds

    def test_skips_default_when_none(self) -> None:
        """default_sink None → no set-default-sink command."""
        state = _AudioState(
            default_sink=None,
            card_profiles={},
            sink_volumes={"analog": "100"},
            sink_mutes={"analog": False},
        )
        with (
            patch("wake_alarm._sinks._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._sinks.subprocess.run") as mock_run,
        ):
            _restore_audio_state(state)
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert not any(c[1] == "set-default-sink" for c in cmds)
        # Unmuted sink restores with "0".
        assert ["/usr/bin/pactl", "set-sink-mute", "analog", "0"] in cmds
