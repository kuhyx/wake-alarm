"""The corner strip's text-free progress row: one pip per morning-session leg.

Split out of ``_session_strip.py`` (250-line cap). The strip shows no words
since 2026-11-10; ``next_step`` in ``morning_session.json`` is still the leg's
label (a data contract), so the pip row finds its place by looking that label
up in ``LEGS``.
"""

from __future__ import annotations

from wake_alarm._session_legs import LEGS

DONE = "●"
NEXT = "◉"
LATER = "○"


def pips(step: object) -> str:
    """Progress pips for ``step`` among the ``LEGS`` labels.

    One plain geometric character per leg (Tk renders no colour emoji):
    filled for legs already passed, a bullseye for the next step, hollow
    for later ones. ``""`` when ``step`` is not a known label.
    """
    labels = [label for _, label in LEGS]
    if not isinstance(step, str) or step not in labels:
        return ""
    idx = labels.index(step)
    return " ".join(
        DONE if i < idx else (NEXT if i == idx else LATER) for i in range(len(labels))
    )
