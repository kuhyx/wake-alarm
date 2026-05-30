"""Dismiss-challenge types for the wake alarm.

Provides three challenge variants:
- math: solve an arithmetic problem
- sort: type shuffled digits in ascending order
- flash: memorise a code before it is hidden
"""

from __future__ import annotations

import secrets

from python_pkg.wake_alarm._constants import DISMISS_CODE_LENGTH, DISMISS_FLASH_SECONDS

# Uppercase alphanumeric chars with visually ambiguous characters removed:
# O/0 (oh vs zero) and I/1 (capital-i vs one) are excluded so the code is
# legible at a glance, even half-asleep.
_DISMISS_CHARS: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class _Challenge:
    """A dismiss challenge presented to the user to prove wakefulness."""

    def __init__(
        self,
        *,
        kind: str,
        display: str,
        answer: str,
        hint: str,
    ) -> None:
        """Store challenge parameters.

        Args:
            kind: Challenge type — "math", "flash", or "sort".
            display: Text shown in the large code label.
            answer: Expected typed answer (normalised, upper-case).
            hint: Short instruction shown above the code label.
        """
        self.kind: str = kind
        self.display: str = display
        self.answer: str = answer
        self.hint: str = hint


def _generate_code() -> str:
    """Generate a random alphanumeric dismiss code.

    Uses uppercase letters and digits only, with ambiguous characters
    (O, I, 0, 1) removed so the displayed code is easy to read at a glance.
    """
    return "".join(secrets.choice(_DISMISS_CHARS) for _ in range(DISMISS_CODE_LENGTH))


def _make_math_challenge() -> _Challenge:
    """Generate an arithmetic problem the user must solve to dismiss.

    Picks randomly from addition, subtraction, and multiplication.
    The user types only the numeric answer — no copying, no autopilot.
    """
    op = secrets.choice(("+", "-", "*"))
    if op == "+":
        a, b = 10 + secrets.randbelow(90), 10 + secrets.randbelow(90)
        return _Challenge(
            kind="math",
            display=f"{a} + {b} = ?",
            answer=str(a + b),
            hint="Solve and type the answer",
        )
    if op == "-":
        a = 20 + secrets.randbelow(80)
        b = 10 + secrets.randbelow(a - 10)
        return _Challenge(
            kind="math",
            display=f"{a} - {b} = ?",
            answer=str(a - b),
            hint="Solve and type the answer",
        )
    a, b = 12 + secrets.randbelow(14), 3 + secrets.randbelow(7)
    return _Challenge(
        kind="math",
        display=f"{a} * {b} = ?",
        answer=str(a * b),
        hint="Solve and type the answer",
    )


def _make_sort_challenge() -> _Challenge:
    """Generate a sort-the-digits challenge.

    Displays six shuffled single digits; the user types them ascending (no spaces).
    Requires a brief cognitive effort — fast enough to be fair, slow enough to prove
    you are awake.
    """
    pool = list(range(1, 10))
    for i in range(len(pool) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        pool[i], pool[j] = pool[j], pool[i]
    digits = pool[:6]
    display = "  ".join(str(d) for d in digits)
    answer = "".join(str(d) for d in sorted(digits))
    return _Challenge(
        kind="sort",
        display=display,
        answer=answer,
        hint="Type digits sorted lowest → highest (no spaces)",
    )


def _make_flash_challenge() -> _Challenge:
    """Generate a memorise-then-type challenge.

    Shows a code for DISMISS_FLASH_SECONDS, then hides it.
    The user must type the code from memory.
    """
    code = _generate_code()
    return _Challenge(
        kind="flash",
        display=code,
        answer=code,
        hint=f"Memorise this code — it disappears in {DISMISS_FLASH_SECONDS}s",
    )


def _make_challenge() -> _Challenge:
    """Pick a random challenge type and generate an instance."""
    return secrets.choice(
        (_make_math_challenge, _make_flash_challenge, _make_sort_challenge),
    )()
