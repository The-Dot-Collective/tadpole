"""Shared pytest fixtures for person_matching_synth tests."""

import pytest
from faker import Faker
import random


@pytest.fixture
def faker():
    """Return a Faker instance seeded with 42."""
    fake = Faker(locale="en_GB")
    fake.seed_instance(42)
    return fake


@pytest.fixture
def rng():
    """Return a random.Random instance seeded with 42."""
    return random.Random(42)
    assert cfg.n_persons == 1_000
    assert cfg.error_rate == 0.15
    assert cfg.dl_presence_rate == 0.95


def test_config_validation_rates_bounds():
    with pytest.raises(ValueError):
        GeneratorConfig(error_rate=1.5)
    with pytest.raises(ValueError):
        GeneratorConfig(error_rate=-0.1)
    with pytest.raises(ValueError):
        GeneratorConfig(dl_presence_rate=2.0)
    with pytest.raises(ValueError):
        GeneratorConfig(dl_benign_suffix_mutation_rate=-0.5)


def test_config_validation_quotes_range():
    with pytest.raises(ValueError):
        GeneratorConfig(quotes_per_person_min=5, quotes_per_person_max=3)
    with pytest.raises(ValueError):
        GeneratorConfig(quotes_per_person_min=0)


def test_config_validation_n_persons():
    with pytest.raises(ValueError):
        GeneratorConfig(n_persons=0)
    with pytest.raises(ValueError):
        GeneratorConfig(n_persons=-10)


def test_config_validation_max_errors():
    with pytest.raises(ValueError):
        GeneratorConfig(max_errors_per_appearance=-1)


def test_config_validation_error_type_weights_keys():
    # Only whitelist field keys allowed
    with pytest.raises(ValueError):
        GeneratorConfig(error_type_weights={"unknown_field": {ErrorType.TYPO: 1.0}})
    # Only whitelisted ErrorType keys per field
    bad_weights = default_weights()
    bad_weights["firstname"][ErrorType.MISSING_TOKEN] = 1.0  # not permitted for firstname
    with pytest.raises(ValueError):
        GeneratorConfig(error_type_weights=bad_weights)


def test_config_validation_error_type_weights_non_negative():
    bad_weights = default_weights()
    bad_weights["firstname"][ErrorType.TYPO] = -0.5
    with pytest.raises(ValueError):
        GeneratorConfig(error_type_weights=bad_weights)
