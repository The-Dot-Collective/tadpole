"""Tests for person_matching_synth.base_person module."""

import pytest
from datetime import date
from person_matching_synth.config import GeneratorConfig
from person_matching_synth.base_person import (
    BasePerson,
    Address,
    compute_pk,
    compute_sk,
    generate_base_pool,
)


class TestComputePk:
    """Test PK computation: UPPER(TRIM(dl))[:-2]."""

    def test_returns_trimmed_uppercase_without_last_two_chars(self):
        assert compute_pk("  obrie853146ro01  ") == "OBRIE853146RO"
        assert compute_pk("OBRIE853146RO01") == "OBRIE853146RO"

    def test_returns_none_if_dl_is_none(self):
        assert compute_pk(None) is None

    def test_returns_none_if_dl_empty_after_trim(self):
        assert compute_pk("   ") is None

    def test_short_dl_returns_empty_string(self):
        # 2-char DL → slice[:-2] = ""
        assert compute_pk("AB") == ""


class TestComputeSk:
    """Test SK computation: first_initial + UPPER(TRIM(surname)) + YYYYMMDD."""

    def test_constructs_correct_sk(self):
        dob = date(1985, 3, 14)
        sk = compute_sk("Robert", "O'Brien", dob)
        assert sk == "ROBRIEN19850314"

    def test_strips_and_uppercases_surname(self):
        dob = date(2000, 1, 1)
        sk = compute_sk("Ann", "  smith  ", dob)
        assert sk == "ASMITH20000101"

    def test_first_initial_uppercase(self):
        dob = date(1990, 5, 5)
        sk = compute_sk("alice", "Jones", dob)
        assert sk == "AJONES19900505"


class TestGenerateBasePool:
    """Test base person pool generation."""

    def test_returns_correct_number_of_persons(self, faker, rng):
        config = GeneratorConfig(n_persons=50, seed=42)
        pool = generate_base_pool(config, faker, rng)
        assert len(pool) == 50

    def test_dl_presence_rate_applied(self, faker, rng):
        config = GeneratorConfig(n_persons=1000, dl_presence_rate=0.5, seed=42)
        pool = generate_base_pool(config, faker, rng)
        with_dl = sum(1 for p in pool if p.dl is not None)
        without_dl = sum(1 for p in pool if p.dl is None)
        assert abs(with_dl / 1000 - 0.5) < 0.1  # within 10%

    def test_sk_collision_pairs_created(self, faker, rng):
        config = GeneratorConfig(n_persons=100, sk_collision_rate=0.1, seed=42)
        pool = generate_base_pool(config, faker, rng)
        # Build SK map
        from collections import Counter
        sk_map = Counter(p.sk_truth for p in pool)
        collisions = [sk for sk, cnt in sk_map.items() if cnt > 1]
        # Expect at least one collision given 100 persons and 10% rate
        assert len(collisions) >= 1

    def test_pk_truth_none_when_dl_missing(self, faker, rng):
        config = GeneratorConfig(n_persons=10, dl_presence_rate=0.0, seed=42)
        pool = generate_base_pool(config, faker, rng)
        for person in pool:
            assert person.dl is None
            assert person.pk_truth is None

    def test_pk_truth_computed_when_dl_present(self, faker, rng):
        config = GeneratorConfig(n_persons=10, dl_presence_rate=1.0, seed=42)
        pool = generate_base_pool(config, faker, rng)
        for person in pool:
            assert person.dl is not None
            assert person.pk_truth == compute_pk(person.dl)

    def test_sk_truth_always_defined(self, faker, rng):
        config = GeneratorConfig(n_persons=10, seed=42)
        pool = generate_base_pool(config, faker, rng)
        for person in pool:
            assert person.sk_truth is not None
            assert person.sk_truth == compute_sk(person.firstname, person.surname, person.dob)

    def test_address_is_stable_frozen_dataclass(self, faker, rng):
        config = GeneratorConfig(n_persons=5, seed=42)
        pool = generate_base_pool(config, faker, rng)
        for person in pool:
            assert isinstance(person.address, Address)
            # Address fields are populated
            assert person.address.postcode
