"""Field-level mutation dispatch and whitelist definitions."""

from enum import Enum
from typing import Callable, Literal
import random

from .config import ErrorType
from .noise import (
    apply_typo,
    apply_transposition,
    apply_abbreviation,
    apply_missing_token,
    apply_blank,
    apply_digit_swap,
    apply_case_flip,
    apply_whitespace,
    NoiseNotApplicable,
)

# Per-field permitted error types from §4.2 of the spec.
FIELD_WHITELIST: dict[str, list[ErrorType]] = {
    "firstname": [
        ErrorType.TYPO,
        ErrorType.TRANSPOSITION,
        ErrorType.ABBREVIATION,
        ErrorType.CASE_FLIP,
        ErrorType.BLANK,
    ],
    "surname": [
        ErrorType.TYPO,
        ErrorType.TRANSPOSITION,
        ErrorType.MISSING_TOKEN,
        ErrorType.CASE_FLIP,
        ErrorType.WHITESPACE,
        ErrorType.BLANK,
    ],
    "dateofbirth": [
        ErrorType.DIGIT_SWAP,
        ErrorType.BLANK,
    ],
    "licencenumber": [
        ErrorType.TYPO,
        ErrorType.TRANSPOSITION,
        ErrorType.DIGIT_SWAP,
        ErrorType.WHITESPACE,
        ErrorType.CASE_FLIP,
        ErrorType.BLANK,
    ],
    "postcode": [
        ErrorType.DIGIT_SWAP,
        ErrorType.WHITESPACE,
        ErrorType.CASE_FLIP,
    ],
    "line1": [
        ErrorType.MISSING_TOKEN,
        ErrorType.TYPO,
        ErrorType.WHITESPACE,
    ],
    "line2": [
        ErrorType.MISSING_TOKEN,
        ErrorType.TYPO,
        ErrorType.WHITESPACE,
    ],
}

NOISE_DISPATCH: dict[ErrorType, Callable[[str, random.Random], str]] = {
    ErrorType.TYPO: apply_typo,
    ErrorType.TRANSPOSITION: apply_transposition,
    ErrorType.ABBREVIATION: apply_abbreviation,
    ErrorType.MISSING_TOKEN: apply_missing_token,
    ErrorType.BLANK: apply_blank,
    ErrorType.DIGIT_SWAP: apply_digit_swap,
    ErrorType.CASE_FLIP: apply_case_flip,
    ErrorType.WHITESPACE: apply_whitespace,
}


def mutate_field(
    field_name: str,
    value: str,
    config,
    rng: random.Random,
) -> tuple[str, ErrorType | None]:
    """
    Decide whether to mutate this field this appearance.

    With probability config.error_rate:
        sample an ErrorType from FIELD_WHITELIST[field_name]
        weighted by config.error_type_weights[field_name]
        apply via NOISE_DISPATCH
        return (mutated_value, applied_type)
    Otherwise return (value, None).

    Raises ValueError if field_name is not in FIELD_WHITELIST.
    """
    if field_name not in FIELD_WHITELIST:
        raise ValueError(f"Unknown field for mutation: {field_name}")

    if rng.random() >= config.error_rate:
        return value, None

    # Sample error type with weights
    weights = config.error_type_weights[field_name]
    error_types = list(weights.keys())
    weights_list = [weights[et] for et in error_types]
    chosen = rng.choices(error_types, weights=weights_list, k=1)[0]

    # Apply mutation, retry up to 3 times if not applicable
    for _ in range(3):
        try:
            mutated = NOISE_DISPATCH[chosen](value, rng)
            return mutated, chosen
        except NoiseNotApplicable:
            # Re-sample a different error type on next iteration
            chosen = rng.choices(error_types, weights=weights_list, k=1)[0]
            continue

    # All retries failed — give up and return original
    return value, None


def mutate_dl(
    dl: str | None,
    config,
    rng: random.Random,
) -> tuple[str | None, Literal["benign_suffix", "destructive", "blank", "none"]]:
    """
    DL-specific dispatcher. Implements §4.3.

    Returns the mutated DL and a tag indicating which mutation class fired.
    The tag drives the §3.3 invariant check.
    """
    if dl is None:
        return None, "none"

    # Benign suffix mutation: only last 2 chars change
    if rng.random() < config.dl_benign_suffix_mutation_rate:
        # Mutate only the final two characters (ordinal suffix)
        if len(dl) >= 2:
            suffix = rng.choice(["01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
                                 "11", "12", "13", "14", "15", "16", "17", "18", "19", "20"])
            mutated = dl[:-2] + suffix
            return mutated, "benign_suffix"
        # If too short, fall through

    # General error-rate mutation using the licencenumber whitelist
    if rng.random() < config.error_rate:
        weights = config.error_type_weights["licencenumber"]
        error_types = list(weights.keys())
        weights_list = [weights[et] for et in error_types]
        chosen = rng.choices(error_types, weights=weights_list, k=1)[0]

        for _ in range(3):
            try:
                mutated = NOISE_DISPATCH[chosen](dl, rng)
                # Determine if mutation is destructive (affects first N-2 chars)
                if mutated != dl:
                    if chosen == ErrorType.BLANK:
                        return None, "blank"
                    # Check if any of the first len(dl)-2 chars changed
                    if len(dl) > 2 and mutated[:-2] != dl[:-2]:
                        return mutated, "destructive"
                    else:
                        # Only suffix or whitespace/case changes that don't affect prefix
                        return mutated, "benign_suffix"
            except NoiseNotApplicable:
                chosen = rng.choices(error_types, weights=weights_list, k=1)[0]
                continue

    return dl, "none"
