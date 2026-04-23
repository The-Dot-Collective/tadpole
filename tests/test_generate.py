"""Integration test for full generation pipeline."""

import pytest
import csv
from pathlib import Path
from person_matching_synth.generate import generate
from person_matching_synth.appearance import verify_invariant
from person_matching_synth.config import GeneratorConfig


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "synth_out"


def test_generate_creates_all_files(output_dir):
    """Integration: generate with small n_persons produces 4 table CSVs + ground_truth.csv."""
    config = GeneratorConfig(
        seed=42,
        n_persons=3,
        quotes_per_person_min=2,
        quotes_per_person_max=2,
        error_rate=0.5,
        output_dir=output_dir,
        emit_ground_truth=True,
    )
    paths = generate(config)

    expected_files = [
        "b4c_request_quote.csv",
        "b4c_request_driver.csv",
        "b4c_request_driver_licence.csv",
        "b4c_request_driver_address.csv",
        "ground_truth.csv",
    ]
    for fname in expected_files:
        assert paths[fname].exists(), f"Missing {fname}"

    # All files should be non-empty
    for fname in expected_files:
        assert paths[fname].stat().st_size > 0


def test_row_counts_match_appearance_count(output_dir):
    """Each appearance produces one row per table; counts should be equal."""
    config = GeneratorConfig(
        seed=42,
        n_persons=5,
        quotes_per_person_min=2,
        quotes_per_person_max=3,
        error_rate=0.2,
        output_dir=output_dir,
        emit_ground_truth=True,
    )
    paths = generate(config)

    # Count rows in each table (excluding header)
    def count_rows(path):
        with open(path, newline="", encoding="utf-8") as f:
            return sum(1 for _ in f) - 1

    quote_rows = count_rows(paths["b4c_request_quote.csv"])
    driver_rows = count_rows(paths["b4c_request_driver.csv"])
    licence_rows = count_rows(paths["b4c_request_driver_licence.csv"])
    address_rows = count_rows(paths["b4c_request_driver_address.csv"])
    gt_rows = count_rows(paths["ground_truth.csv"])

    # All table row counts must be equal
    assert quote_rows == driver_rows == licence_rows == address_rows == gt_rows

    # Total rows should be between n_persons*min and n_persons*max
    total_expected_min = 5 * 2
    total_expected_max = 5 * 3
    assert total_expected_min <= quote_rows <= total_expected_max


def test_ground_truth_columns(output_dir):
    """ground_truth.csv has the required columns."""
    config = GeneratorConfig(
        seed=42,
        n_persons=2,
        quotes_per_person_min=1,
        quotes_per_person_max=1,
        error_rate=0.0,
        output_dir=output_dir,
        emit_ground_truth=True,
    )
    paths = generate(config)
    gt_path = paths["ground_truth.csv"]
    with open(gt_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected_cols = {
            "correlationid",
            "driver_id",
            "base_person_id",
            "applied_noise_firstname",
            "applied_noise_surname",
            "applied_noise_dob",
            "applied_noise_dl",
            "dl_mutation_class",
        }
        assert set(reader.fieldnames) == expected_cols


def test_invariant_holds_for_all_appearances(output_dir):
    """Post-hoc: every appearance in the output satisfies verify_invariant."""
    from person_matching_synth.base_person import generate_base_pool
    from person_matching_synth.appearance import build_appearance, IdCounters
    from faker import Faker
    import random

    config = GeneratorConfig(
        seed=42,
        n_persons=10,
        quotes_per_person_min=1,
        quotes_per_person_max=2,
        error_rate=0.3,
        output_dir=output_dir,
        emit_ground_truth=True,
    )
    paths = generate(config)

    # Reconstruct base pool and appearances to verify invariant
    faker = Faker(locale=config.locale)
    faker.seed_instance(config.seed)
    rng = random.Random(config.seed)
    base_pool = generate_base_pool(config, faker, rng)

    # Build a map: base_person_id -> BasePerson
    person_by_id = {p.base_person_id: p for p in base_pool}

    # Read ground_truth.csv to get correlationid + driver_id -> base_person_id mapping
    gt_path = paths["ground_truth.csv"]
    with open(gt_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            base_id = int(row["base_person_id"])
            base_person = person_by_id[base_id]
            # Rebuild the appearance from the driver row to verify invariant
            driver_path = paths["b4c_request_driver.csv"]
            with open(driver_path, newline="", encoding="utf-8") as df:
                dreader = csv.DictReader(df)
                for drow in dreader:
                    if drow["correlationid"] == row["correlationid"] and int(drow["driver_id"]) == int(row["driver_id"]):
                        # Reconstruct observed fields
                        from datetime import datetime
                        dob_str = drow["dateofbirth"]
                        dob_observed = datetime.strptime(dob_str, "%Y-%m-%d %H:%M:%S").date() if dob_str else None
                        # DL from licence table
                        lic_path = paths["b4c_request_driver_licence.csv"]
                        with open(lic_path, newline="", encoding="utf-8") as lf:
                            lreader = csv.DictReader(lf)
                            dl_observed = None
                            for lrow in lreader:
                                if lrow["correlationid"] == row["correlationid"] and int(lrow["driver_id"]) == int(row["driver_id"]):
                                    lic_num = lrow["licencenumber"]
                                    dl_observed = lic_num if lic_num else None
                                    break
                        # Build minimal appearance object for invariant check
                        from person_matching_synth.appearance import QuoteAppearance
                        appearance = QuoteAppearance(
                            correlationid=row["correlationid"],
                            quote_header_id="",  # not needed
                            id=0,  # not needed
                            driver_id=int(row["driver_id"]),
                            driver_license_id=0,
                            driver_address_id=0,
                            base_person_id=base_id,
                            firstname_observed=drow["firstname"],
                            surname_observed=drow["surname"],
                            dob_observed=dob_observed,
                            dl_observed=dl_observed,
                            applied_noise={},
                            quote_row={},
                            driver_row={},
                            licence_row={},
                            address_row={},
                        )
                        assert verify_invariant(base_person, appearance), (
                            f"Invariant failed for base_person_id={base_id}, "
                            f"driver_id={row['driver_id']}, correlationid={row['correlationid']}"
                        )
                        break
                else:
                    pytest.fail(f"Driver row not found for {row}")


def test_reproducibility_same_seed_same_output(output_dir):
    """Two runs with identical seed/config produce byte-identical output."""
    config1 = GeneratorConfig(
        seed=12345,
        n_persons=10,
        quotes_per_person_min=2,
        quotes_per_person_max=3,
        error_rate=0.3,
        output_dir=output_dir / "run1",
        emit_ground_truth=True,
    )
    config2 = GeneratorConfig(
        seed=12345,
        n_persons=10,
        quotes_per_person_min=2,
        quotes_per_person_max=3,
        error_rate=0.3,
        output_dir=output_dir / "run2",
        emit_ground_truth=True,
    )
    paths1 = generate(config1)
    paths2 = generate(config2)

    for key in paths1:
        p1 = paths1[key]
        p2 = paths2[key]
        assert p1.read_bytes() == p2.read_bytes(), f"File {key} differs between runs"
