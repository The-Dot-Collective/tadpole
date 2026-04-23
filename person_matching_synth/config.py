"""Configuration and enumerations for the synthetic data generator."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Literal


class ErrorType(Enum):
    """Permitted error types for noise injection."""
    TYPO = "TYPO"
    TRANSPOSITION = "TRANSPOSITION"
    ABBREVIATION = "ABBREVIATION"
    MISSING_TOKEN = "MISSING_TOKEN"
    BLANK = "BLANK"
    DIGIT_SWAP = "DIGIT_SWAP"
    CASE_FLIP = "CASE_FLIP"
    WHITESPACE = "WHITESPACE"


# Per-field whitelist of permitted error types (§4.2)
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


def default_weights() -> dict[str, dict[ErrorType, float]]:
    """
    Return the per-field error-type weight table from §4.2.
    Equal weights within each field's permitted set.
    """
    return {
        field: {err_type: 1.0 for err_type in FIELD_WHITELIST[field]}
        for field in FIELD_WHITELIST
    }


@dataclass(frozen=True)
class GeneratorConfig:
    """All configurable parameters for the synthetic data generator."""
    seed: int = 42
    n_persons: int = 1_000
    quotes_per_person_min: int = 1
    quotes_per_person_max: int = 8
    error_rate: float = 0.15
    error_type_weights: dict[str, dict[ErrorType, float]] = field(default_factory=default_weights)
    dl_presence_rate: float = 0.95
    dl_benign_suffix_mutation_rate: float = 0.10
    sk_collision_rate: float = 0.01
    max_errors_per_appearance: int = 2
    allow_unrecoverable_appearances: bool = False
    locale: str = "en_GB"
    output_dir: Path = Path("./synth_out")
    emit_ground_truth: bool = True

    def __post_init__(self) -> None:
        # Validate numeric bounds
        if not (0.0 <= self.error_rate <= 1.0):
            raise ValueError(f"error_rate must be in [0.0, 1.0], got {self.error_rate}")
        if not (0.0 <= self.dl_presence_rate <= 1.0):
            raise ValueError(f"dl_presence_rate must be in [0.0, 1.0], got {self.dl_presence_rate}")
        if not (0.0 <= self.dl_benign_suffix_mutation_rate <= 1.0):
            raise ValueError(f"dl_benign_suffix_mutation_rate must be in [0.0, 1.0], got {self.dl_benign_suffix_mutation_rate}")
        if not (0.0 <= self.sk_collision_rate <= 1.0):
            raise ValueError(f"sk_collision_rate must be in [0.0, 1.0], got {self.sk_collision_rate}")
        if self.quotes_per_person_min < 1:
            raise ValueError(f"quotes_per_person_min must be >= 1, got {self.quotes_per_person_min}")
        if self.quotes_per_person_max < self.quotes_per_person_min:
            raise ValueError(f"quotes_per_person_max ({self.quotes_per_person_max}) must be >= quotes_per_person_min ({self.quotes_per_person_min})")
        if self.n_persons < 1:
            raise ValueError(f"n_persons must be >= 1, got {self.n_persons}")
        if self.max_errors_per_appearance < 0:
            raise ValueError(f"max_errors_per_appearance must be >= 0, got {self.max_errors_per_appearance}")

        # Validate error_type_weights structure
        whitelist_fields = set(FIELD_WHITELIST.keys())
        config_fields = set(self.error_type_weights.keys())
        if not config_fields.issubset(whitelist_fields):
            extra = config_fields - whitelist_fields
            raise ValueError(f"error_type_weights contains unknown fields: {extra}")

        for field_name, weights in self.error_type_weights.items():
            allowed = set(FIELD_WHITELIST[field_name])
            given = set(weights.keys())
            if not given.issubset(allowed):
                extra_types = given - allowed
                raise ValueError(f"error_type_weights['{field_name}'] contains unknown ErrorTypes: {extra_types}")
            if not all(w >= 0 for w in weights.values()):
                raise ValueError(f"error_type_weights['{field_name}'] must have non-negative weights")
            if sum(weights.values()) <= 0:
                raise ValueError(f"error_type_weights['{field_name}'] must have at least one positive weight")
