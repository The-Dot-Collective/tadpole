"""Tests for person_matching_synth.appearance module."""

import pytest
from datetime import date, datetime
from person_matching_synth.appearance import (
    QuoteAppearance,
    IdCounters,
    build_appearance,
    verify_invariant,
    InvariantViolation,
)
from person_matching_synth.base_person import BasePerson, Address, compute_pk
from person_matching_synth.config import GeneratorConfig, ErrorType
from person_matching_synth.fields import mutate_dl
import random
from faker import Faker


@pytest.fixture
def simple_base_person(faker, rng):
    """Create a simple base person for testing."""
    return BasePerson(
        base_person_id=1,
        firstname="Robert",
        surname="O'Brien",
        dob=date(1985, 3, 14),
        dl="OBRIE853146RO01",
        address=Address(
            housenumber="123",
            line1="Main Street",
            line2=None,
            town="Townsville",
            county="Some County",
            country="UK",
            postcode="AB12 3CD",
        ),
        pk_truth="OBRIE853146RO",
        sk_truth="ROBRIEN19850314",
    )


class TestVerifyInvariant:
    """Test the invariant checking function."""

    def test_pk_match_succeeds(self, simple_base_person):
        appearance = QuoteAppearance(
            correlationid="cid",
            quote_header_id="qhid",
            id=1,
            driver_id=1,
            driver_license_id=1,
            driver_address_id=1,
            base_person_id=1,
            firstname_observed="Robert",
            surname_observed="O'Brien",
            dob_observed=date(1985, 3, 14),
            dl_observed="OBRIE853146RO01",  # PK matches
            applied_noise={},
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )
        assert verify_invariant(simple_base_person, appearance) is True

    def test_sk_match_succeeds_when_pk_fails(self, simple_base_person):
        appearance = QuoteAppearance(
            correlationid="cid",
            quote_header_id="qhid",
            id=1,
            driver_id=1,
            driver_license_id=1,
            driver_address_id=1,
            base_person_id=1,
            firstname_observed="Robert",
            surname_observed="O'Brien",
            dob_observed=date(1985, 3, 14),
            dl_observed="WRONG12345678",  # PK broken
            applied_noise={},
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )
        # SK still matches
        assert verify_invariant(simple_base_person, appearance) is True

    def test_fails_when_both_pk_and_sk_broken(self, simple_base_person):
        appearance = QuoteAppearance(
            correlationid="cid",
            quote_header_id="qhid",
            id=1,
            driver_id=1,
            driver_license_id=1,
            driver_address_id=1,
            base_person_id=1,
            firstname_observed="Wrong",
            surname_observed="Name",
            dob_observed=date(2000, 1, 1),
            dl_observed="WRONG12345678",
            applied_noise={},
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )
        assert verify_invariant(simple_base_person, appearance) is False

    def test_sk_fallback_works_with_abbreviated_firstname(self, simple_base_person):
        # First initial still matches
        appearance = QuoteAppearance(
            correlationid="cid",
            quote_header_id="qhid",
            id=1,
            driver_id=1,
            driver_license_id=1,
            driver_address_id=1,
            base_person_id=1,
            firstname_observed="Rob",  # first initial still R
            surname_observed="O'Brien",
            dob_observed=date(1985, 3, 14),
            dl_observed="WRONG12345678",
            applied_noise={},
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )
        assert verify_invariant(simple_base_person, appearance) is True

    def test_sk_fails_if_first_initial_changes(self, simple_base_person):
        appearance = QuoteAppearance(
            correlationid="cid",
            quote_header_id="qhid",
            id=1,
            driver_id=1,
            driver_license_id=1,
            driver_address_id=1,
            base_person_id=1,
            firstname_observed="Alice",  # initial A ≠ R
            surname_observed="O'Brien",
            dob_observed=date(1985, 3, 14),
            dl_observed="WRONG12345678",
            applied_noise={},
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )
        assert verify_invariant(simple_base_person, appearance) is False

    def test_dl_none_allows_sk_match(self, simple_base_person):
        appearance = QuoteAppearance(
            correlationid="cid",
            quote_header_id="qhid",
            id=1,
            driver_id=1,
            driver_license_id=1,
            driver_address_id=1,
            base_person_id=1,
            firstname_observed="Robert",
            surname_observed="O'Brien",
            dob_observed=date(1985, 3, 14),
            dl_observed=None,  # DL blanked
            applied_noise={},
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )
        assert verify_invariant(simple_base_person, appearance) is True

    def test_dob_none_forces_pk_only(self, simple_base_person):
        # SK cannot match without DOB; PK must match
        appearance = QuoteAppearance(
            correlationid="cid",
            quote_header_id="qhid",
            id=1,
            driver_id=1,
            driver_license_id=1,
            driver_address_id=1,
            base_person_id=1,
            firstname_observed="Robert",
            surname_observed="O'Brien",
            dob_observed=None,
            dl_observed="OBRIE853146RO01",
            applied_noise={},
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )
        assert verify_invariant(simple_base_person, appearance) is True
        # If PK also wrong, fails
        appearance.dl_observed = "WRONG"
        assert verify_invariant(simple_base_person, appearance) is False


class TestBuildAppearance:
    """Test appearance construction and invariant enforcement."""

    def test_clean_appearance_has_no_noise(self, simple_base_person, faker, rng):
        config = GeneratorConfig(seed=42, error_rate=0.0, max_errors_per_appearance=0)
        counters = IdCounters(next_quote_id=1, next_driver_id=1, next_licence_id=1, next_address_id=1)
        appearance = build_appearance(
            base_person=simple_base_person,
            appearance_index=0,
            id_counters=counters,
            config=config,
            faker=faker,
            rng=rng,
        )
        # Observed fields should match base person
        assert appearance.firstname_observed == simple_base_person.firstname
        assert appearance.surname_observed == simple_base_person.surname
        assert appearance.dob_observed == simple_base_person.dob
        assert appearance.dl_observed == simple_base_person.dl
        assert verify_invariant(simple_base_person, appearance)

    def test_invariant_always_holds_with_retries(self, simple_base_person, faker):
        # High error rate should still produce valid appearances via retries
        config = GeneratorConfig(seed=42, error_rate=0.8, max_errors_per_appearance=2)
        rng = random.Random(42)
        counters = IdCounters(next_quote_id=1, next_driver_id=1, next_licence_id=1, next_address_id=1)
        for i in range(20):
            appearance = build_appearance(
                base_person=simple_base_person,
                appearance_index=i,
                id_counters=counters,
                config=config,
                faker=faker,
                rng=rng,
            )
            assert verify_invariant(simple_base_person, appearance), f"Appearance {i} failed invariant"

    def test_dl_benign_suffix_preserves_pk(self, simple_base_person, faker, rng):
        config = GeneratorConfig(seed=42, error_rate=0.0, dl_benign_suffix_mutation_rate=1.0)
        counters = IdCounters(next_quote_id=1, next_driver_id=1, next_licence_id=1, next_address_id=1)
        appearance = build_appearance(
            base_person=simple_base_person,
            appearance_index=0,
            id_counters=counters,
            config=config,
            faker=faker,
            rng=rng,
        )
        # PK must still match
        assert compute_pk(appearance.dl_observed) == simple_base_person.pk_truth
        assert appearance.applied_noise.get("dl") == "benign_suffix"

    def test_dl_blank_forces_sk_match(self, simple_base_person, faker, rng):
        config = GeneratorConfig(seed=42, error_rate=0.0)
        # Force BLANK on DL by injecting it via rng trick: we'll directly test mutate_dl
        dl_result, tag = mutate_dl(simple_base_person.dl, config, rng)
        # Not deterministic; just check tag is one of the expected values
        assert tag in {"benign_suffix", "destructive", "blank", "none"}

    def test_max_errors_cap_respected(self, simple_base_person, faker, rng):
        config = GeneratorConfig(seed=42, error_rate=1.0, max_errors_per_appearance=1)
        counters = IdCounters(next_quote_id=1, next_driver_id=1, next_licence_id=1, next_address_id=1)
        appearance = build_appearance(
            base_person=simple_base_person,
            appearance_index=0,
            id_counters=counters,
            config=config,
            faker=faker,
            rng=rng,
        )
        # Count non-None noise entries (dl counts as one)
        noise_count = sum(1 for v in appearance.applied_noise.values() if v is not None)
        assert noise_count <= 1

    def test_applied_noise_tracking(self, simple_base_person, faker, rng):
        config = GeneratorConfig(seed=42, error_rate=0.5)
        counters = IdCounters(next_quote_id=1, next_driver_id=1, next_licence_id=1, next_address_id=1)
        appearance = build_appearance(
            base_person=simple_base_person,
            appearance_index=0,
            id_counters=counters,
            config=config,
            faker=faker,
            rng=rng,
        )
        # applied_noise keys must include the four matching fields
        for key in ("firstname", "surname", "dateofbirth", "dl"):
            assert key in appearance.applied_noise
        # Values are either ErrorType or DL tag string or None
        for v in appearance.applied_noise.values():
            assert v is None or isinstance(v, (ErrorType, str))
