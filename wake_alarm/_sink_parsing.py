"""Parsing the text ``pactl`` prints — cards, profiles and sinks.

Split out of ``_sinks.py`` for the 250-line cap. This half is pure text
handling with no subprocess and no side effects, so it is testable without
touching the host's audio at all; ``_sinks.py`` keeps the command execution
and the activate/restore orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


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
