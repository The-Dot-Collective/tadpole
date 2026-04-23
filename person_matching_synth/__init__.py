# Person-Matching Synthetic Data Generator
# Produces configurable synthetic quote data for validating the deterministic
# Person-matching algorithm (truncated DL + SK composite).

from .config import GeneratorConfig, ErrorType, default_weights
from .base_person import BasePerson, Address, generate_base_pool, compute_pk, compute_sk
from .noise import NoiseNotApplicable, apply_typo, apply_transposition, apply_abbreviation
from .noise import apply_missing_token, apply_blank, apply_digit_swap, apply_case_flip
from .noise import apply_whitespace, NOISE_DISPATCH
from .fields import FIELD_WHITELIST, mutate_field, mutate_dl
from .appearance import QuoteAppearance, IdCounters, build_appearance, verify_invariant
from .emit import write_tables
from .generate import generate

__all__ = [
    "GeneratorConfig",
    "ErrorType",
    "default_weights",
    "BasePerson",
    "Address",
    "generate_base_pool",
    "compute_pk",
    "compute_sk",
    "NoiseNotApplicable",
    "NOISE_DISPATCH",
    "FIELD_WHITELIST",
    "mutate_field",
    "mutate_dl",
    "QuoteAppearance",
    "IdCounters",
    "build_appearance",
    "verify_invariant",
    "write_tables",
    "generate",
]
