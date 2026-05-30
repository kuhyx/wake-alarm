"""Tests for _challenges.py — dismiss challenge generators."""

from __future__ import annotations

from unittest.mock import patch

from python_pkg.wake_alarm._challenges import (
    _DISMISS_CHARS,
    _Challenge,
    _make_challenge,
    _make_flash_challenge,
    _make_math_challenge,
    _make_sort_challenge,
)
from python_pkg.wake_alarm._constants import DISMISS_FLASH_SECONDS


class TestMakeMathChallenge:
    """Tests for _make_math_challenge."""

    def test_kind_is_math(self) -> None:
        """Challenge kind is always 'math'."""
        assert _make_math_challenge().kind == "math"

    def test_answer_is_correct_for_addition(self) -> None:
        """Stored answer is numerically correct for addition."""
        with (
            patch("python_pkg.wake_alarm._challenges.secrets.choice", return_value="+"),
            patch(
                "python_pkg.wake_alarm._challenges.secrets.randbelow",
                side_effect=[13, 35],  # 10+13=23, 10+35=45
            ),
        ):
            ch = _make_math_challenge()
        assert ch.display == "23 + 45 = ?"
        assert ch.answer == "68"

    def test_answer_is_correct_for_subtraction(self) -> None:
        """Stored answer is numerically correct for subtraction."""
        with (
            patch("python_pkg.wake_alarm._challenges.secrets.choice", return_value="-"),
            patch(
                "python_pkg.wake_alarm._challenges.secrets.randbelow",
                side_effect=[30, 7],  # 20+30=50, 10+7=17
            ),
        ):
            ch = _make_math_challenge()
        assert ch.display == "50 - 17 = ?"
        assert ch.answer == "33"

    def test_answer_is_correct_for_multiplication(self) -> None:
        """Stored answer is numerically correct for multiplication."""
        with (
            patch("python_pkg.wake_alarm._challenges.secrets.choice", return_value="*"),
            patch(
                "python_pkg.wake_alarm._challenges.secrets.randbelow",
                side_effect=[3, 4],  # 12+3=15, 3+4=7
            ),
        ):
            ch = _make_math_challenge()
        assert ch.display == "15 * 7 = ?"
        assert ch.answer == "105"

    def test_answer_varies_across_calls(self) -> None:
        """Multiple calls produce varied answers (probabilistic)."""
        answers = {_make_math_challenge().answer for _ in range(30)}
        assert len(answers) > 1


class TestMakeSortChallenge:
    """Tests for _make_sort_challenge."""

    def test_kind_is_sort(self) -> None:
        """Challenge kind is always 'sort'."""
        assert _make_sort_challenge().kind == "sort"

    def test_answer_is_sorted_digits(self) -> None:
        """Answer equals the digits in display sorted ascending."""
        ch = _make_sort_challenge()
        displayed_digits = [int(c) for c in ch.display if c.isdigit()]
        expected = "".join(str(d) for d in sorted(displayed_digits))
        assert ch.answer == expected

    def test_display_contains_six_digits(self) -> None:
        """Display always contains exactly six digit characters."""
        ch = _make_sort_challenge()
        assert len([c for c in ch.display if c.isdigit()]) == 6

    def test_answer_varies_across_calls(self) -> None:
        """Multiple calls produce varied digit sets."""
        answers = {_make_sort_challenge().answer for _ in range(30)}
        assert len(answers) > 1


class TestMakeFlashChallenge:
    """Tests for _make_flash_challenge."""

    def test_kind_is_flash(self) -> None:
        """Challenge kind is always 'flash'."""
        assert _make_flash_challenge().kind == "flash"

    def test_display_equals_answer(self) -> None:
        """Display and answer are identical (the user must recall the full code)."""
        ch = _make_flash_challenge()
        assert ch.display == ch.answer

    def test_code_uses_dismiss_chars(self) -> None:
        """Generated code only contains chars from _DISMISS_CHARS."""
        ch = _make_flash_challenge()
        assert all(c in _DISMISS_CHARS for c in ch.answer)

    def test_hint_mentions_flash_seconds(self) -> None:
        """Hint text includes the number of visible seconds."""
        ch = _make_flash_challenge()
        assert str(DISMISS_FLASH_SECONDS) in ch.hint


class TestMakeChallenge:
    """Tests for _make_challenge (the random dispatcher)."""

    def test_returns_a_challenge(self) -> None:
        """Returns a _Challenge instance with all expected fields populated."""
        ch = _make_challenge()
        assert isinstance(ch, _Challenge)
        assert ch.kind in ("math", "flash", "sort")
        assert ch.display
        assert ch.answer
        assert ch.hint

    def test_all_types_reachable(self) -> None:
        """All three challenge types appear across many calls."""
        kinds = {_make_challenge().kind for _ in range(200)}
        assert kinds == {"math", "flash", "sort"}
