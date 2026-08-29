"""PipeWire sink/card enumeration, activation, and restore for the wake alarm.

At wake time the Bluetooth speaker is gone and WirePlumber leaves most card
profiles ``off``, so the machine is silent. This module forces every card's
output on, unmutes and maxes every sink, and captures the prior state so the
alarm can restore it on dismiss. The alarm plays on *all* sinks every beep
cycle (see :func:`wake_alarm._audio._play_on_all_sinks`) rather than betting on
a single chosen output.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import shutil
import subprocess

from wake_alarm._constants import (
    ALARM_AUDIO_SINK,
)
from wake_alarm._sink_parsing import (
    _CardAccum,
    _CardInfo,
    _parse_cards,
    _parse_sinks,
)

# Imported under their original names because the suite patches
# `wake_alarm._sinks._parse_cards` and friends: a moved symbol makes patch()
# stop intercepting *silently*. __all__ stops ruff deleting them as unused.
__all__ = ["_CardAccum", "_CardInfo", "_parse_cards", "_parse_sinks"]

_logger = logging.getLogger(__name__)


def _pactl_path() -> str | None:
    """Return the absolute path to pactl, or None when not installed."""
    return shutil.which("pactl")


def _pactl_text(pactl: str, *args: str, timeout: float = 5.0) -> str | None:
    """Run ``pactl <args>`` and return decoded stdout, or None on failure."""
    try:
        result = subprocess.run(
            [pactl, *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        _logger.warning("pactl %s failed", " ".join(args), exc_info=True)
        return None
    return result.stdout.decode(errors="replace")


def _list_real_sinks(pactl: str) -> list[str]:
    """Return every non-``auto_null`` sink name from ``pactl list short sinks``."""
    text = _pactl_text(pactl, "list", "short", "sinks")
    if text is None:
        return []
    names = [line.split("\t")[1] for line in text.splitlines() if "\t" in line]
    return [name for name in names if name != "auto_null"]


def _list_cards(pactl: str) -> list[str]:
    """Return every card name from ``pactl list short cards``."""
    text = _pactl_text(pactl, "list", "short", "cards")
    if text is None:
        return []
    return [line.split("\t")[1] for line in text.splitlines() if "\t" in line]


def _current_default_sink(pactl: str) -> str | None:
    """Return the current default sink name, or None on failure / empty."""
    try:
        result = subprocess.run(
            [pactl, "get-default-sink"],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        _logger.warning("pactl get-default-sink failed", exc_info=True)
        return None
    name = result.stdout.decode(errors="replace").strip()
    return name or None


def _ensure_sink_audible(pactl: str, sink: str) -> None:
    """Unmute *sink* and raise it to 100%, so playback on it is actually heard."""
    for args in (
        ["set-sink-mute", sink, "0"],
        ["set-sink-volume", sink, "100%"],
    ):
        subprocess.run(
            [pactl, *args],
            capture_output=True,
            timeout=3,
            check=False,
        )


@dataclass
class _AudioState:
    """Snapshot of audio state to restore after the alarm is dismissed."""

    default_sink: str | None
    card_profiles: dict[str, str]  # card name -> active profile
    sink_volumes: dict[str, str]  # sink name -> raw first-channel volume
    sink_mutes: dict[str, bool]  # sink name -> muted?


def _capture_audio_state(pactl: str) -> _AudioState:
    """Capture every card profile, sink volume/mute, and the default sink."""
    cards = _parse_cards(_pactl_text(pactl, "list", "cards") or "")
    card_profiles = {
        name: info.active_profile
        for name, info in cards.items()
        if info.active_profile is not None
    }
    sink_volumes, sink_mutes = _parse_sinks(_pactl_text(pactl, "list", "sinks") or "")
    return _AudioState(
        default_sink=_current_default_sink(pactl),
        card_profiles=card_profiles,
        sink_volumes=sink_volumes,
        sink_mutes=sink_mutes,
    )


def _activate_all_outputs() -> _AudioState | None:
    """Turn on every card's output and make every sink audible for the alarm.

    At wake time the Bluetooth speaker is gone and WirePlumber leaves most card
    profiles ``off``, so the alarm is silent. This forces every card's best
    output profile on, then unmutes and raises every sink to 100%. The alarm
    then plays on *all* sinks every beep cycle
    (:func:`wake_alarm._audio._play_on_all_sinks`) — it does not pick one output
    and hope: a switched-off external speaker cannot be revived by software, so
    every *other* output is tried in parallel instead.

    It does not block waiting for the known-slow ``ALARM_AUDIO_SINK`` (the G27Q
    monitor's HDMI speaker, ~15 s to enumerate); it activates whatever is present
    now and lets the per-cycle presence check in ``_play_on_all_sinks`` sweep in
    the rest. The default sink, when set, is only a convenience — per-cycle
    all-sink playback is what guarantees audio.

    Returns:
        The prior audio state (to restore on close), or ``None`` only when
        pactl is unavailable (nothing was changed, so nothing to restore).
    """
    pactl = _pactl_path()
    if pactl is None:
        _logger.warning("pactl not on PATH; cannot activate alarm audio")
        return None
    state = _capture_audio_state(pactl)
    for card, info in _parse_cards(_pactl_text(pactl, "list", "cards") or "").items():
        if info.output_profiles:
            subprocess.run(
                [pactl, "set-card-profile", card, info.output_profiles[0]],
                capture_output=True,
                timeout=3,
                check=False,
            )
    # No sleep-and-hope wait. Forcing the profiles on above makes sinks appear
    # asynchronously (the monitor's HDMI sink can take ~15 s), but we don't block
    # on a timer guessing when it's "ready". We activate whatever is present
    # right now; the beep loop's _play_on_all_sinks re-checks _list_real_sinks
    # every cycle, so each output is made audible and played on the moment it
    # actually exists — a real presence check, never a timed guess.
    sinks = _list_real_sinks(pactl)
    if not sinks:
        _logger.warning(
            "No real sink present yet; the beep loop will pick sinks up as they "
            "enumerate (PC speaker covers the gap).",
        )
        return state
    for sink in sinks:
        _ensure_sink_audible(pactl, sink)
    default = ALARM_AUDIO_SINK if ALARM_AUDIO_SINK in sinks else sinks[0]
    subprocess.run(
        [pactl, "set-default-sink", default],
        capture_output=True,
        timeout=3,
        check=False,
    )
    _logger.warning(
        "Alarm audio activated on %d present sink(s) at 100%%, default=%s; more "
        "are added by the beep loop as they enumerate.",
        len(sinks),
        default,
    )
    return state


def _restore_audio_state(state: _AudioState | None) -> None:
    """Restore card profiles, sink volumes/mutes, and default captured earlier."""
    if state is None:
        return
    pactl = _pactl_path()
    if pactl is None:
        return
    for card, profile in state.card_profiles.items():
        subprocess.run(
            [pactl, "set-card-profile", card, profile],
            capture_output=True,
            timeout=3,
            check=False,
        )
    for sink, volume in state.sink_volumes.items():
        subprocess.run(
            [pactl, "set-sink-volume", sink, volume],
            capture_output=True,
            timeout=3,
            check=False,
        )
    for sink, muted in state.sink_mutes.items():
        subprocess.run(
            [pactl, "set-sink-mute", sink, "1" if muted else "0"],
            capture_output=True,
            timeout=3,
            check=False,
        )
    if state.default_sink is not None:
        subprocess.run(
            [pactl, "set-default-sink", state.default_sink],
            capture_output=True,
            timeout=3,
            check=False,
        )


def _warn_if_no_real_sink() -> None:
    """Log a warning when PipeWire has no real (non-auto_null) sink yet.

    Informational only: :func:`_activate_all_outputs` runs afterwards and forces
    card profiles on, so a missing sink here is not necessarily fatal.
    """
    pactl = _pactl_path()
    if pactl is None:
        _logger.warning("pactl not on PATH; cannot verify audio sinks")
        return
    real_sinks = _list_real_sinks(pactl)
    if not real_sinks:
        _logger.warning(
            "No real PipeWire sink yet — alarm will force card profiles on and "
            "fall back to the PC speaker.",
        )
    else:
        _logger.info("Audio sinks available: %s", real_sinks)
