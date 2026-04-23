"""Tests for person_matching_synth.noise module."""

import pytest
import random
from person_matching_synth.noise import (
    apply_typo,
    apply_transposition,
    apply_abbreviation,
    apply_missing_token,
    apply_blank,
    apply_digit_swap,
    apply_case_flip,
    apply_whitespace,
    NoiseNotApplicable,
    NOISE_DISPATCH,
)


class TestNoiseFunctions:
    """Unit tests for each noise function."""

    def test_apply_typo_changes_one_character(self):
        rng = random.Random(42)
        original = "Robert"
        mutated = apply_typo(original, rng)
        assert len(mutated) == len(original)
        assert mutated != original
        # Only one character differs
        diffs = sum(1 for a, b in zip(original, mutated) if a != b)
        assert diffs == 1

    def test_apply_typo_empty_input(self):
        rng = random.Random(42)
        assert apply_typo("", rng) == ""

    def test_apply_transposition_swaps_adjacent_pair(self):
        rng = random.Random(42)
        original = "ABCD"
        mutated = apply_transposition(original, rng)
        assert len(mutated) == len(original)
        # Exactly one adjacent swap occurred
        swap_count = sum(1 for i in range(len(original)-1) if mutated[i] == original[i+1] and mutated[i+1] == original[i])
        assert swap_count == 1

    def test_apply_transposition_raises_on_single_char(self):
        rng = random.Random(42)
        with pytest.raises(NoiseNotApplicable):
            apply_transposition("X", rng)

    def test_apply_abbreviation_shortens_forename(self):
        rng = random.Random(42)
        # Known forename
        assert apply_abbreviation("Robert", rng) in {"Rob", "Bob", "Bert", "R"}
        # Unknown forename falls back to first initial
        assert apply_abbreviation("X Æ A-12", rng) == "X"

    def test_apply_abbreviation_empty_input(self):
        rng = random.Random(42)
        assert apply_abbreviation("", rng) == ""

    def test_apply_missing_token_drops_one_token(self):
        rng = random.Random(42)
        original = "Flat 2A 123 Main Street"
        mutated = apply_missing_token(original, rng)
        tokens_original = original.split()
        tokens_mutated = mutated.split()
        assert len(tokens_mutated) == len(tokens_original) - 1
        # All tokens from mutated must appear in original in same order
        assert all(tok in tokens_original for tok in tokens_mutated)

    def test_apply_missing_token_raises_on_single_token(self):
        rng = random.Random(42)
        with pytest.raises(NoiseNotApplicable):
            apply_missing_token("OnlyOneToken", rng)

    def test_apply_blank_returns_empty(self):
        rng = random.Random(42)
        assert apply_blank("anything", rng) == ""

    def test_apply_digit_swap_changes_one_digit(self):
        rng = random.Random(42)
        original = "12345"
        mutated = apply_digit_swap(original, rng)
        assert len(mutated) == len(original)
        assert all(c.isdigit() for c in mutated)
        diffs = sum(1 for a, b in zip(original, mutated) if a != b)
        assert diffs == 1

    def test_apply_digit_swap_no_digits_raises(self):
        rng = random.Random(42)
        with pytest.raises(NoiseNotApplicable):
            apply_digit_swap("ABCDE", rng)

    def test_apply_case_flip_inverts_some_case(self):
        rng = random.Random(42)
        original = "Hello World"
        mutated = apply_case_flip(original, rng)
        assert len(mutated) == len(original)
        # At least one character's case differs
        assert any(a != b and a.lower() == b.lower() for a, b in zip(original, mutated))

    def test_apply_whitespace_adds_space(self):
        rng = random.Random(42)
        original = "text"
        mutated = apply_whitespace(original, rng)
        assert mutated in {" text", "text "}

    def test_idempotency_with_same_rng_state(self):
        """Given the same rng state, each function produces identical output."""
        rng1 = random.Random(123)
        rng2 = random.Random(123)
        assert apply_typo("Robert", rng1) == apply_typo("Robert", rng2)
        assert apply_transposition("ABCD", rng1) == apply_transposition("ABCD", rng2)
        assert apply_abbreviation("Robert", rng1) == apply_abbreviation("Robert", rng2)
        assert apply_blank("X", rng1) == apply_blank("X", rng2)
        assert apply_digit_swap("123", rng1) == apply_digit_swap("123", rng2)
        assert apply_case_flip("AbC", rng1) == apply_case_flip("AbC", rng2)
        assert apply_whitespace("hi", rng1) == apply_whitespace("hi", rng2)

    def test_noise_dispatch_coverage(self):
        """NOISE_DISPATCH maps every ErrorType to a callable."""
        from person_matching_synth.config import ErrorType
        for err_type in ErrorType:
            assert err_type in NOISE_DISPATCH
            assert callable(NOISE_DISPATCH[err_type])
