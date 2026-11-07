"""The leg names and labels the PC reads must equal the phone's enum.

``fixtures/session_legs.json`` is one literal both sides assert: this test
against ``_session_legs.LEGS`` and ``phone_app/test/services/
session_legs_fixture_test.dart`` against ``SessionLeg``. Each side's own
round-trip cannot catch a naming drift with its sibling.
"""

from __future__ import annotations

import json
from pathlib import Path

from wake_alarm._session_legs import LEGS, next_step

FIXTURE = Path(__file__).parent / "fixtures" / "session_legs.json"


def test_legs_equal_the_shared_fixture() -> None:
    legs = json.loads(FIXTURE.read_text(encoding="utf-8"))["legs"]
    assert [(leg["name"], leg["label"]) for leg in legs] == list(LEGS)


def test_next_step_is_the_first_leg_not_passed() -> None:
    assert next_step(()) == "Tap the bathroom tag"
    assert next_step(("bathroomIn",)) == "Shower, then tap the bathroom tag again"
    # Order of the legs decides, not the order they were passed in.
    assert next_step(("showerDone",)) == "Tap the bathroom tag"
    assert next_step(("atDesk", "bathroomIn", "showerDone", "dressed")) is None
    assert next_step(("unknownLeg",)) == "Tap the bathroom tag"
