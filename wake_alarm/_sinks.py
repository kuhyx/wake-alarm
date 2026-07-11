"""PipeWire sink/card enumeration, activation, and restore for the wake alarm.

At wake time the Bluetooth speaker is gone and WirePlumber leaves most card
profiles ``off``, so the machine is silent. This module forces every card's
output on, unmutes and maxes every sink, and captures the prior state so the
alarm can restore it on dismiss. The alarm plays on *all* sinks every beep
cycle (see :func:`wake_alarm._audio._play_on_all_sinks`) rather than betting on
a single chosen output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
import shutil
import subprocess
import time

from wake_alarm._constants import (
    ALARM_AUDIO_SINK,
    ALARM_AUDIO_SINK_POLL_SECONDS,
    ALARM_AUDIO_SINK_WAIT_SECONDS,
)

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
    except (OSError, subprocess.TimeoutExpired):
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
    except (OSError, subprocess.TimeoutExpired):
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


def _parse_profile_line(line: str) -> tuple[str, int] | None:
    """Parse one ``output:*`` profile line into ``(name, priority)``.

    Returns None for non-output profiles and for profiles marked
    ``available: no`` (an output whose sink cannot currently be produced,
    e.g. an HDMI port with nothing plugged in).
    """
    if not line.startswith("output:"):
        return None
    name, sep, rest = line.partition(": ")
    if not sep or "available: no" in rest:
        return None
    match = re.search(r"priority:\s*(\d+)", rest)
    priority = int(match.group(1)) if match else 0
    return name, priority


@dataclass
class _CardInfo:
    """A card's active profile and its available ``output:*`` profiles."""

    active_profile: str | None
    # Available output profiles, best first (stereo preferred, then priority).
    output_profiles: list[str]


@dataclass
class _CardAccum:
    """Mutable accumulator for one card block while parsing ``list cards``."""

    name: str | None = None
    active: str | None = None
    profiles: list[tuple[str, int]] = field(default_factory=list)


def _parse_cards(text: str) -> dict[str, _CardInfo]:
    """Parse ``pactl list cards`` (full) into ``{card_name: _CardInfo}``."""
    cards: dict[str, _CardInfo] = {}
    cur: _CardAccum | None = None
    in_profiles = False
    for raw in text.splitlines():
        if raw.startswith("Card #"):
            _store_card(cards, cur)
            cur = _CardAccum()
            in_profiles = False
            continue
        if cur is None:
            continue
        stripped = raw.strip()
        if stripped.startswith("Name:"):
            cur.name = stripped.split(":", 1)[1].strip()
            in_profiles = False
        elif stripped.startswith("Active Profile:"):
            cur.active = stripped.split(":", 1)[1].strip()
            in_profiles = False
        elif stripped == "Profiles:":
            in_profiles = True
        elif in_profiles:
            parsed = _parse_profile_line(stripped)
            if parsed is not None:
                cur.profiles.append(parsed)
    _store_card(cards, cur)
    return cards


def _store_card(cards: dict[str, _CardInfo], cur: _CardAccum | None) -> None:
    """Finalise one parsed card block and add it to *cards* (skip if unnamed)."""
    if cur is None or cur.name is None:
        return
    # Prefer a stereo profile, then the highest priority.
    ordered = sorted(
        cur.profiles, key=lambda np: (0 if "stereo" in np[0] else 1, -np[1])
    )
    cards[cur.name] = _CardInfo(
        active_profile=cur.active,
        output_profiles=[profile for profile, _ in ordered],
    )


def _parse_sinks(text: str) -> tuple[dict[str, str], dict[str, bool]]:
    """Parse ``pactl list sinks`` into ``({sink: raw_volume}, {sink: muted})``."""
    volumes: dict[str, str] = {}
    mutes: dict[str, bool] = {}
    name: str | None = None
    for raw in text.splitlines():
        if raw.startswith("Sink #"):
            name = None
            continue
        stripped = raw.strip()
        if stripped.startswith("Name:"):
            name = stripped.split(":", 1)[1].strip()
        elif name is None:
            continue
        elif stripped.startswith("Mute:"):
            mutes[name] = stripped.split(":", 1)[1].strip() == "yes"
        elif stripped.startswith("Volume:"):
            match = re.search(r"(\d+)", stripped)
            if match:
                volumes[name] = match.group(1)
    return volumes, mutes


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

    It waits (bounded) for the known-slow ``ALARM_AUDIO_SINK`` (the G27Q
    monitor's HDMI speaker, ~15 s to enumerate after power-on) so that output is
    included in the first pass; the default sink is set to it when present but is
    only a convenience — per-cycle all-sink playback is what guarantees audio.

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
    # Wait for the known always-on monitor sink specifically, not just "any"
    # sink: a switched-off external speaker often leaves a live-but-silent sink
    # already present, and breaking on that would route the alarm to the dead
    # output (the exact silent-alarm failure this change fixes). Fall back to
    # whatever sinks exist if the monitor never enumerates.
    attempts = max(
        1,
        int(ALARM_AUDIO_SINK_WAIT_SECONDS / ALARM_AUDIO_SINK_POLL_SECONDS),
    )
    sinks: list[str] = []
    for _ in range(attempts):
        sinks = _list_real_sinks(pactl)
        if ALARM_AUDIO_SINK in sinks:
            break
        time.sleep(ALARM_AUDIO_SINK_POLL_SECONDS)
    else:
        _logger.warning(
            "Preferred sink %s did not appear after %.0fs; using whatever exists",
            ALARM_AUDIO_SINK,
            ALARM_AUDIO_SINK_WAIT_SECONDS,
        )
        sinks = _list_real_sinks(pactl)
    if not sinks:
        _logger.warning("No real sink available; alarm relies on PC speaker")
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
        "Alarm audio activated on %d sink(s) at 100%%, default=%s",
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
