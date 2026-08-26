"""Tests for pactl sink/card enumeration, activation, and restore."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from wake_alarm._gating import parse_args as _parse_args
from wake_alarm._sinks import (
    _capture_audio_state,
    _current_default_sink,
    _list_cards,
    _list_real_sinks,
    _pactl_text,
    _parse_cards,
    _parse_profile_line,
    _parse_sinks,
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


class TestPactlText:
    """Tests for _pactl_text."""

    def test_returns_decoded_stdout(self) -> None:
        """Success → decoded stdout string."""
        proc = MagicMock(stdout=b"hello\n")
        with patch("wake_alarm._sinks.subprocess.run", return_value=proc):
            assert _pactl_text("/usr/bin/pactl", "info") == "hello\n"

    def test_returns_none_on_error(self) -> None:
        """OSError/TimeoutExpired → None, no raise."""
        with patch(
            "wake_alarm._sinks.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pactl", 5),
        ):
            assert _pactl_text("/usr/bin/pactl", "info") is None


class TestPactlPath:
    """Tests for _pactl_path."""

    def test_returns_which_result(self) -> None:
        """Delegates to shutil.which('pactl')."""
        from wake_alarm._sinks import _pactl_path

        with patch(
            "wake_alarm._sinks.shutil.which",
            return_value="/usr/bin/pactl",
        ):
            assert _pactl_path() == "/usr/bin/pactl"


class TestListRealSinks:
    """Tests for _list_real_sinks."""

    def test_filters_auto_null(self) -> None:
        """auto_null is dropped; real sink names are returned."""
        text = (
            "62\talsa_output.analog\tPipeWire\t-\t-\n4319\tauto_null\tPipeWire\t-\t-\n"
        )
        with patch("wake_alarm._sinks._pactl_text", return_value=text):
            assert _list_real_sinks("/usr/bin/pactl") == ["alsa_output.analog"]

    def test_returns_empty_on_none(self) -> None:
        """pactl failure (None text) → empty list."""
        with patch("wake_alarm._sinks._pactl_text", return_value=None):
            assert _list_real_sinks("/usr/bin/pactl") == []


class TestListCards:
    """Tests for _list_cards."""

    def test_parses_names(self) -> None:
        """Returns the card name column of `list short cards`."""
        text = "54\talsa_card.hdmi\talsa\n55\talsa_card.mic\talsa\n"
        with patch("wake_alarm._sinks._pactl_text", return_value=text):
            assert _list_cards("/usr/bin/pactl") == [
                "alsa_card.hdmi",
                "alsa_card.mic",
            ]

    def test_returns_empty_on_none(self) -> None:
        """pactl failure (None text) → empty list."""
        with patch("wake_alarm._sinks._pactl_text", return_value=None):
            assert _list_cards("/usr/bin/pactl") == []


class TestParseProfileLine:
    """Tests for _parse_profile_line."""

    def test_non_output_returns_none(self) -> None:
        """A non-output profile line → None."""
        assert _parse_profile_line("off: Off (available: yes)") is None

    def test_unavailable_returns_none(self) -> None:
        """An output profile marked available: no → None."""
        assert _parse_profile_line("output:x: X (available: no)") is None

    def test_missing_colon_space_returns_none(self) -> None:
        """An output line with no ': ' separator → None."""
        assert _parse_profile_line("output:x") is None

    def test_defaults_priority_zero(self) -> None:
        """An available output with no priority field → priority 0."""
        assert _parse_profile_line("output:x: X (available: yes)") == ("output:x", 0)

    def test_parses_priority(self) -> None:
        """Priority is parsed from the line."""
        assert _parse_profile_line(
            "output:hdmi: HDMI (priority: 5900, available: yes)",
        ) == ("output:hdmi", 5900)


class TestParseCards:
    """Tests for _parse_cards."""

    def test_parses_and_skips_edge_cases(self) -> None:
        """Stereo preferred, input-only card empty, unnamed card skipped."""
        cards = _parse_cards(_CARDS_TEXT)
        assert set(cards) == {"alsa_card.hdmi", "alsa_card.mic"}
        assert cards["alsa_card.hdmi"].active_profile == "off"
        assert cards["alsa_card.hdmi"].output_profiles == ["output:hdmi-stereo"]
        assert cards["alsa_card.mic"].output_profiles == []

    def test_ignores_lines_before_first_card(self) -> None:
        """Leading noise before the first `Card #` is ignored."""
        assert _parse_cards("junk\nmore junk\n") == {}


class TestParseSinks:
    """Tests for _parse_sinks."""

    def test_parses_volume_and_mute(self) -> None:
        """Captures first raw volume and mute state per sink."""
        volumes, mutes = _parse_sinks(_SINKS_TEXT)
        assert volumes["alsa_output.analog"] == "65536"
        assert mutes == {"alsa_output.analog": False, "alsa_output.weird": True}

    def test_volume_without_digit_is_skipped(self) -> None:
        """A Volume line with no integer is not recorded."""
        volumes, _ = _parse_sinks(_SINKS_TEXT)
        assert "alsa_output.weird" not in volumes


class TestCurrentDefaultSink:
    """Tests for _current_default_sink."""

    def test_returns_sink_name(self) -> None:
        """Returns the trimmed default sink name."""
        proc = MagicMock(stdout=b"jbl_sink\n")
        with patch("wake_alarm._sinks.subprocess.run", return_value=proc):
            assert _current_default_sink("/usr/bin/pactl") == "jbl_sink"

    def test_returns_none_when_empty(self) -> None:
        """Empty output → None."""
        proc = MagicMock(stdout=b"\n")
        with patch("wake_alarm._sinks.subprocess.run", return_value=proc):
            assert _current_default_sink("/usr/bin/pactl") is None

    def test_returns_none_on_error(self) -> None:
        """TimeoutExpired → None, no raise."""
        with patch(
            "wake_alarm._sinks.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pactl", 3),
        ):
            assert _current_default_sink("/usr/bin/pactl") is None


class TestCaptureAudioState:
    """Tests for _capture_audio_state."""

    def test_captures_profiles_volumes_mutes_default(self) -> None:
        """Combines card profiles, sink volumes/mutes, and the default sink."""
        with (
            patch(
                "wake_alarm._sinks._pactl_text",
                side_effect=[_CARDS_TEXT, _SINKS_TEXT],
            ),
            patch(
                "wake_alarm._sinks._current_default_sink",
                return_value="alsa_output.analog",
            ),
        ):
            state = _capture_audio_state("/usr/bin/pactl")
        assert state.default_sink == "alsa_output.analog"
        assert state.card_profiles["alsa_card.hdmi"] == "off"
        assert state.sink_volumes["alsa_output.analog"] == "65536"
        assert state.sink_mutes["alsa_output.analog"] is False


class TestParseArgs:
    """Tests for _parse_args."""

    def test_default_flags_are_false(self) -> None:
        """No CLI args means every flag is False."""
        ns = _parse_args([])
        assert ns.demo is False
        assert ns.trigger_now is False
        assert ns.production is False

    def test_flags_parse(self) -> None:
        """Each flag flips to True when passed."""
        ns = _parse_args(["--production", "--demo", "--trigger-now"])
        assert ns.production is True
        assert ns.demo is True
        assert ns.trigger_now is True
