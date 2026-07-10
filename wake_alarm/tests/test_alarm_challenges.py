"""Tests for _challenges.py — dismiss challenge generators."""

from __future__ import annotations

from unittest.mock import patch

from wake_alarm._challenges import (
    _DISMISS_CHARS,
    _REVERSE_WORDS,
    _Challenge,
    _make_challenge,
    _make_flash_challenge,
    _make_math_challenge,
    _make_reverse_challenge,
    _make_sequence_challenge,
    _make_sort_challenge,
)
from wake_alarm._constants import DISMISS_FLASH_SECONDS


class TestMakeMathChallenge:
    """Tests for _make_math_challenge."""

    def test_kind_is_math(self) -> None:
        """Challenge kind is always 'math'."""
        assert _make_math_challenge().kind == "math"

    def test_answer_is_correct_for_addition(self) -> None:
        """Stored answer is numerically correct for addition."""
        with (
            patch("wake_alarm._challenges.secrets.choice", return_value="+"),
            patch(
                "wake_alarm._challenges.secrets.randbelow",
                side_effect=[100, 200],  # 100+100=200, 100+200=300
            ),
        ):
            ch = _make_math_challenge()
        assert ch.display == "200 + 300 = ?"
        assert ch.answer == "500"

    def test_answer_is_correct_for_subtraction(self) -> None:
        """Stored answer is numerically correct for subtraction."""
        with (
            patch("wake_alarm._challenges.secrets.choice", return_value="-"),
            patch(
                "wake_alarm._challenges.secrets.randbelow",
                side_effect=[100, 50],  # 200+100=300, 100+50=150
            ),
        ):
            ch = _make_math_challenge()
        assert ch.display == "300 - 150 = ?"
        assert ch.answer == "150"

    def test_answer_is_correct_for_multiplication(self) -> None:
        """Stored answer is numerically correct for multiplication."""
        with (
            patch("wake_alarm._challenges.secrets.choice", return_value="*"),
            patch(
                "wake_alarm._challenges.secrets.randbelow",
                side_effect=[3, 4],  # 12+3=15, 3+4=7
            ),
        ):
            ch = _make_math_challenge()
        assert ch.display == "15 * 7 = ?"
        assert ch.answer == "105"

    def test_answer_is_correct_for_division(self) -> None:
        """Stored answer is numerically correct for division (always integer)."""
        with (
            patch("wake_alarm._challenges.secrets.choice", return_value="÷"),
            patch(
                "wake_alarm._challenges.secrets.randbelow",
                side_effect=[2, 5],  # b=3+2=5, a=(10+5)*5=75
            ),
        ):
            ch = _make_math_challenge()
        assert ch.display == "75 ÷ 5 = ?"
        assert ch.answer == "15"

    def test_division_answer_is_always_integer(self) -> None:
        """Division challenges always produce whole-number answers."""
        for _ in range(30):
            with patch("wake_alarm._challenges.secrets.choice", return_value="÷"):
                ch = _make_math_challenge()
            # Extract dividend and divisor from display
            parts = ch.display.replace(" ÷ ", " ").replace(" = ?", "").split()
            dividend, divisor = int(parts[0]), int(parts[1])
            assert dividend % divisor == 0

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

    def test_display_contains_eight_digits(self) -> None:
        """Display always contains exactly eight digit characters."""
        ch = _make_sort_challenge()
        assert len([c for c in ch.display if c.isdigit()]) == 8

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


class TestMakeSequenceChallenge:
    """Tests for _make_sequence_challenge."""

    def test_kind_is_sequence(self) -> None:
        """Challenge kind is always 'sequence'."""
        assert _make_sequence_challenge().kind == "sequence"

    def test_arithmetic_answer_is_correct(self) -> None:
        """Arithmetic sequence next term is first + step * 4."""
        with patch("wake_alarm._challenges.secrets.randbelow", side_effect=[0, 0, 3]):
            # randbelow(2)==0 → arithmetic, start=2+0=2, step=2+3=5
            ch = _make_sequence_challenge()
        assert ch.display == "2, 7, 12, 17, ?"
        assert ch.answer == "22"

    def test_geometric_answer_is_correct(self) -> None:
        """Geometric sequence next term is start * ratio^4."""
        with patch("wake_alarm._challenges.secrets.randbelow", side_effect=[1, 0, 0]):
            # randbelow(2)==1 → geometric, start=2+0=2, ratio=2+0=2
            ch = _make_sequence_challenge()
        assert ch.display == "2, 4, 8, 16, ?"
        assert ch.answer == "32"

    def test_answer_is_last_term(self) -> None:
        """The answer is always the 5th term of the displayed sequence."""
        for _ in range(30):
            ch = _make_sequence_challenge()
            # Re-derive from the display
            terms_str = ch.display.replace(", ?", "").split(", ")
            terms = [int(t) for t in terms_str]
            assert len(terms) == 4
            # Arithmetic check: constant difference
            diffs = [terms[i + 1] - terms[i] for i in range(3)]
            if len(set(diffs)) == 1:
                expected = terms[-1] + diffs[0]
            else:
                # Geometric: constant ratio
                ratio = terms[1] // terms[0]
                expected = terms[-1] * ratio
            assert ch.answer == str(expected)

    def test_both_series_types_reachable(self) -> None:
        """Both arithmetic and geometric series appear across many calls."""
        found_arithmetic = False
        found_geometric = False
        for _ in range(200):
            ch = _make_sequence_challenge()
            terms_str = ch.display.replace(", ?", "").split(", ")
            terms = [int(t) for t in terms_str]
            diffs = [terms[i + 1] - terms[i] for i in range(3)]
            if len(set(diffs)) == 1:
                found_arithmetic = True
            else:
                found_geometric = True
            if found_arithmetic and found_geometric:
                break
        assert found_arithmetic
        assert found_geometric


class TestMakeReverseChallenge:
    """Tests for _make_reverse_challenge."""

    def test_kind_is_reverse(self) -> None:
        """Challenge kind is always 'reverse'."""
        assert _make_reverse_challenge().kind == "reverse"

    def test_answer_is_word_reversed(self) -> None:
        """Answer equals the displayed word reversed."""
        ch = _make_reverse_challenge()
        # Extract the word from display (second line)
        word = ch.display.split("\n")[1]
        assert ch.answer == word[::-1]

    def test_word_is_from_pool(self) -> None:
        """Displayed word always comes from _REVERSE_WORDS."""
        ch = _make_reverse_challenge()
        word = ch.display.split("\n")[1]
        assert word in _REVERSE_WORDS

    def test_answer_varies_across_calls(self) -> None:
        """Multiple calls produce different words (probabilistic)."""
        answers = {_make_reverse_challenge().answer for _ in range(60)}
        assert len(answers) > 1


class TestMakeChallenge:
    """Tests for _make_challenge (the random dispatcher)."""

    def test_returns_a_challenge(self) -> None:
        """Returns a _Challenge instance with all expected fields populated."""
        ch = _make_challenge()
        assert isinstance(ch, _Challenge)
        assert ch.kind in ("math", "flash", "sort", "sequence", "reverse")
        assert ch.display
        assert ch.answer
        assert ch.hint

    def test_all_types_reachable(self) -> None:
        """All five challenge types appear across many calls."""
        kinds = {_make_challenge().kind for _ in range(500)}
        assert kinds == {"math", "flash", "sort", "sequence", "reverse"}
