"""The morning session's legs, in order, as the phone names and labels them.

Mirrors ``SessionLeg`` and ``SessionLegSlot.label`` in
``phone_app/lib/services/morning_session.dart``. A leg's *name* is the key of
the phone's ``passed`` map; its *label* is what the PC's ``next_step`` shows.
``tests/fixtures/session_legs.json`` is asserted by a Python and a Dart test,
so a rename on one side fails the other's build.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection

LEGS: tuple[tuple[str, str], ...] = (
    ("bathroomIn", "Tap the bathroom tag"),
    ("showerDone", "Shower, then tap the bathroom tag again"),
    ("dressed", "Get dressed — tap the wardrobe tag"),
    ("atDesk", "Sit down — tap the desk tag"),
)


def next_step(passed: Collection[str]) -> str | None:
    """Label of the first leg (in order) not in ``passed``; None when all are."""
    for name, label in LEGS:
        if name not in passed:
            return label
    return None
