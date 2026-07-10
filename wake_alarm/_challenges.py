"""Dismiss-challenge types for the wake alarm.

Provides five challenge variants:
- math: solve an arithmetic problem (addition, subtraction, multiplication, division)
- sort: type shuffled digits in ascending order
- flash: memorise a code before it is hidden
- sequence: identify and continue a numeric pattern
- reverse: type a displayed word backwards
"""

from __future__ import annotations

import secrets

from wake_alarm._constants import DISMISS_CODE_LENGTH, DISMISS_FLASH_SECONDS

# Uppercase alphanumeric chars with visually ambiguous characters removed:
# O/0 (oh vs zero) and I/1 (capital-i vs one) are excluded so the code is
# legible at a glance, even half-asleep.
_DISMISS_CHARS: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Words used by the reverse challenge — common, unambiguous when read half-asleep.
_REVERSE_WORDS: tuple[str, ...] = (
    "MORNING",
    "COFFEE",
    "PILLOW",
    "BLANKET",
    "ALARM",
    "AWAKE",
    "SHOWER",
    "BREAKFAST",
    "WORKOUT",
    "WINDOW",
    "MONDAY",
    "TUESDAY",
    "FRIDAY",
    "SUNDAY",
    "WEEKEND",
)


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
            kind: Challenge type — "math", "flash", "sort", "sequence", or "reverse".
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

    Picks randomly from addition, subtraction, multiplication, and division.
    Addition and subtraction use 3-digit operands for extra difficulty.
    Division always produces an integer result.
    """
    op = secrets.choice(("+", "-", "*", "÷"))
    if op == "+":
        a = 100 + secrets.randbelow(400)
        b = 100 + secrets.randbelow(400)
        return _Challenge(
            kind="math",
            display=f"{a} + {b} = ?",
            answer=str(a + b),
            hint="Solve and type the answer",
        )
    if op == "-":
        a = 200 + secrets.randbelow(300)
        b = 100 + secrets.randbelow(a - 100)
        return _Challenge(
            kind="math",
            display=f"{a} - {b} = ?",
            answer=str(a - b),
            hint="Solve and type the answer",
        )
    if op == "*":
        a = 12 + secrets.randbelow(14)
        b = 3 + secrets.randbelow(7)
        return _Challenge(
            kind="math",
            display=f"{a} * {b} = ?",
            answer=str(a * b),
            hint="Solve and type the answer",
        )
    # Division: construct a * b first so the quotient is always an integer.
    b = 3 + secrets.randbelow(8)  # divisor: 3-10
    a = (10 + secrets.randbelow(20)) * b  # dividend: b * (10-29)
    return _Challenge(
        kind="math",
        display=f"{a} ÷ {b} = ?",
        answer=str(a // b),
        hint="Solve and type the answer",
    )


def _make_sort_challenge() -> _Challenge:
    """Generate a sort-the-digits challenge.

    Displays eight shuffled single digits; the user types them ascending (no spaces).
    Eight digits (up from six) require more effort to sort mentally.
    """
    pool = list(range(1, 10))
    for i in range(len(pool) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        pool[i], pool[j] = pool[j], pool[i]
    digits = pool[:8]
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


def _make_sequence_challenge() -> _Challenge:
    """Generate a numeric-pattern completion challenge.

    Shows four terms of an arithmetic or geometric sequence and asks for the fifth.
    Forces the user to identify the pattern before they can answer.
    """
    if secrets.randbelow(2) == 0:
        # Arithmetic sequence (linear)
        start = 2 + secrets.randbelow(14)  # start: 2-15
        step = 2 + secrets.randbelow(8)  # step: 2-9
        terms = [start + step * i for i in range(4)]
        answer = start + step * 4
        display = ", ".join(str(t) for t in terms) + ", ?"
        return _Challenge(
            kind="sequence",
            display=display,
            answer=str(answer),
            hint="Find the pattern and type the next number",
        )
    # Geometric sequence (exponential)
    start = 2 + secrets.randbelow(5)  # start: 2-6
    ratio = 2 + secrets.randbelow(2)  # ratio: 2 or 3
    terms = [start * (ratio**i) for i in range(4)]
    answer = start * (ratio**4)
    display = ", ".join(str(t) for t in terms) + ", ?"
    return _Challenge(
        kind="sequence",
        display=display,
        answer=str(answer),
        hint="Find the pattern and type the next number",
    )


def _make_reverse_challenge() -> _Challenge:
    """Generate a reverse-the-word challenge.

    Picks a common word and asks the user to type it backwards.
    Simple but demands conscious attention — autopilot types forward.
    """
    word = secrets.choice(_REVERSE_WORDS)
    return _Challenge(
        kind="reverse",
        display=f"Type this word backwards:\n{word}",
        answer=word[::-1],
        hint="Type the word backwards",
    )


def _make_challenge() -> _Challenge:
    """Pick a random challenge type and generate an instance."""
    return secrets.choice(
        (
            _make_math_challenge,
            _make_flash_challenge,
            _make_sort_challenge,
            _make_sequence_challenge,
            _make_reverse_challenge,
        ),
    )()
