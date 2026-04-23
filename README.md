# Person-Matching Synthetic Data Generator

A configurable Python library that produces synthetic quote data across four relational tables for validating deterministic Person-matching algorithms. The generator creates realistic UK PII with controlled noise injection, ensuring that each base person remains matchable via either Primary Key (truncated driving licence) or Secondary Key (first-initial + surname + date of birth) across clean and noisy appearances.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Usage](#usage)
- [Output](#output)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Matching Algorithm Contract](#matching-algorithm-contract)
- [Development](#development)

## Overview

### Purpose

This generator is designed to create test data for a record-linkage system that matches person records across multiple insurance quote submissions. The matching algorithm under test uses two keys:

- **Primary Key (PK)**: Normalised driving licence number (`UPPER(TRIM(dl))[0:-2]`)
- **Secondary Key (SK)**: Composite of first initial, normalised surname, and date of birth (`first_initial + UPPER(TRIM(surname)) + YYYYMMDD`)

The generator guarantees that for every base person, at least one of these keys remains recoverable across all appearances, even after noise injection.

### Key Features

- **Deterministic seeding**: Fully reproducible runs via configurable RNG seeds
- **Realistic UK PII**: Uses Faker with `en_GB` locale for authentic names, addresses, postcodes, and dates of birth
- **Configurable noise model**: Per-field error types with adjustable rates (typo, transposition, abbreviation, digit-swap, case-flip, whitespace, missing token, blank)
- **SK collision support**: Optional generation of distinct base persons sharing identical SK (same first initial + surname + DOB) with different driving licences
- **Ground truth sidecar**: Emits `ground_truth.csv` mapping each appearance back to its canonical base person and documenting applied noise
- **Invariant enforcement**: Retries appearance generation until PK or SK matchability is satisfied (or max retries exceeded)

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd tadpole

# Install dependencies (requires Python 3.11+)
pip install -e ".[dev]"
```

### Basic Usage

```python
from person_matching_synth import generate, GeneratorConfig

config = GeneratorConfig(
    seed=42,
    n_persons=1000,
    quotes_per_person_min=1,
    quotes_per_person_max=8,
    error_rate=0.15,
    output_dir="./synth_out",
)

paths = generate(config)
print(f"Generated files: {paths}")
```

### CLI

```bash
python -m person_matching_synth.generate --seed 42 --n-persons 1000 --error-rate 0.15
```

## Architecture

The generator follows a clean, layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    generate.py (Orchestrator)               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 1. Seed RNGs (Faker + random.Random)                 │  │
│  │ 2. generate_base_pool() → list[BasePerson]            │  │
│  │ 3. For each base person: draw n_appearances           │  │
│  │ 4. build_appearance() → QuoteAppearance               │  │
│  │ 5. write_tables() → CSV files                         │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  base_person.py          │  appearance.py                    │
│  • BasePerson (identity) │  • QuoteAppearance (row builder)  │
│  • compute_pk()          │  • verify_invariant()             │
│  • compute_sk()          │  • IdCounters (monotonic IDs)     │
│  • generate_base_pool()  │                                   │
├─────────────────────────────────────────────────────────────┤
│  config.py               │  noise.py                         │
│  • GeneratorConfig       │  • 8 pure noise functions         │
│  • ErrorType enum        │  • NOISE_DISPATCH                 │
│  • FIELD_WHITELIST       │                                   │
│  • default_weights()     │                                   │
├─────────────────────────────────────────────────────────────┤
│  fields.py               │  emit.py                          │
│  • mutate_field()        │  • write_tables()                 │
│  • mutate_dl()           │    (CSV streaming)                │
│  • per-field dispatch    │                                   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Base Person Generation** (`base_person.py`)
   - Draws identity atoms (firstname, surname, DOB, address) from Faker
   - Applies `dl_presence_rate` to decide if a driving licence exists
   - Generates UK driving licence numbers via `_generate_dl()`
   - Optionally creates SK collisions by cloning identity from existing pool members
   - Computes `pk_truth` and `sk_truth` for each base person

2. **Appearance Construction** (`appearance.py`)
   - For each base person, draws a random number of appearances (quotes)
   - For each appearance, applies field-level noise according to `error_rate` and per-field whitelists
   - Enforces the invariant: at least one of PK or SK must match the base person truth
   - Retries up to `MAX_RETRIES` (10) if invariant fails; raises `InvariantViolation` if exhausted
   - Populates all four table rows with deterministic IDs and plausible context fields

3. **CSV Emission** (`emit.py`)
   - Streams all appearances to four CSV files matching production DDL schemas
   - Optionally writes `ground_truth.csv` with debugging columns

## Configuration

`GeneratorConfig` exposes all tunable parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `seed` | `int` | `42` | RNG seed for full reproducibility |
| `n_persons` | `int` | `1000` | Number of distinct base persons to generate |
| `quotes_per_person_min` | `int` | `1` | Minimum appearances per person |
| `quotes_per_person_max` | `int` | `8` | Maximum appearances per person |
| `error_rate` | `float` | `0.15` | Probability of applying noise to any given matching field |
| `error_type_weights` | `dict` | per-field equal | Relative weights for each permitted `ErrorType` per field |
| `dl_presence_rate` | `float` | `0.95` | Fraction of base persons with a driving licence |
| `dl_benign_suffix_mutation_rate` | `float` | `0.10` | Rate of last-2-char mutations that preserve PK |
| `sk_collision_rate` | `float` | `0.01` | Probability that a new person clones SK from an existing one |
| `max_errors_per_appearance` | `int` | `2` | Maximum number of fields to mutate per appearance |
| `allow_unrecoverable_appearances` | `bool` | `False` | If True, invariant enforcement is skipped |
| `locale` | `str` | `"en_GB"` | Faker locale for PII generation |
| `output_dir` | `Path` | `"./synth_out"` | Directory for CSV output |
| `emit_ground_truth` | `bool` | `True` | Whether to write `ground_truth.csv` |

### Error Types

Each matching field has a whitelist of permitted noise types (defined in `config.py` and `fields.py`):

| ErrorType | Description | Applicable Fields |
|---|---|---|
| `TYPO` | Single-character substitution via QWERTY adjacency | firstname, surname, licencenumber |
| `TRANSPOSITION` | Swap two adjacent characters | firstname, surname, licencenumber |
| `ABBREVIATION` | Replace with common UK short form | firstname |
| `MISSING_TOKEN` | Remove one character | surname, line1, line2 |
| `BLANK` | Replace with empty string | firstname, surname, dateofbirth, licencenumber |
| `DIGIT_SWAP` | Swap two adjacent digits | dateofbirth, licencenumber, postcode |
| `CASE_FLIP` | Toggle case of one character | firstname, surname, licencenumber |
| `WHITESPACE` | Insert or delete a space | surname, licencenumber, postcode |

## Usage

### Python API

```python
from pathlib import Path
from person_matching_synth import generate, GeneratorConfig

config = GeneratorConfig(
    seed=12345,
    n_persons=500,
    quotes_per_person_min=2,
    quotes_per_person_max=5,
    error_rate=0.20,
    dl_presence_rate=0.90,
    sk_collision_rate=0.02,
    output_dir=Path("./my_output"),
)

output_paths = generate(config)
# Returns dict: {
#   "b4c_request_quote": Path(...),
#   "b4c_request_driver": Path(...),
#   "b4c_request_driver_licence": Path(...),
#   "b4c_request_driver_address": Path(...),
#   "ground_truth": Path(...),
# }
```

### Command Line

```bash
python -m person_matching_synth.generate \
  --seed 42 \
  --n-persons 1000 \
  --min-quotes 1 \
  --max-quotes 8 \
  --error-rate 0.15 \
  --output-dir ./synth_out
```

### Customising Noise Weights

```python
from person_matching_synth.config import ErrorType, default_weights

# Start from defaults
weights = default_weights()

# Increase typo weight for firstname
weights["firstname"][ErrorType.TYPO] = 2.0
weights["firstname"][ErrorType.ABBREVIATION] = 0.5  # decrease abbreviation

config = GeneratorConfig(
    error_type_weights=weights,
    # ... other params
)
```

## Output

Four CSV tables are produced, mirroring production schemas:

### `b4c_request_quote.csv`

One row per quote. Contains correlation IDs, timestamps, and contextual fields.

| Column | Description |
|---|---|
| `id` | Monotonic quote identifier (PK) |
| `quote_header_id` | UUID4 — quote-level identifier |
| `correlationid` | UUID4 — shared across all four tables for the same quote |
| `brand`, `source`, `channel`, `line`, `offering` | Contextual categorisation |
| `source_timestamp` | Quote creation time |
| `shredding_timestamp` | `source_timestamp + 1 day` |
| `startdate`, `coverlevel`, `paymentfrequency`, `voluntaryexcess` | Plausible defaults |

### `b4c_request_driver.csv`

One row per driver appearance. Contains the matching fields (`firstname`, `surname`, `dateofbirth`) plus extensive context.

| Column | Notes |
|---|---|
| `driver_id` | Monotonic per-appearance identifier |
| `pcr_drvid` | `"DRV-" + driver_id` |
| `firstname`, `surname`, `dateofbirth` | Matching fields — may be mutated by noise |
| `title`, `gender`, `maritalstatus` | Contextual demographics |
| `ismaindriver`, `isproposer` | Role flags (usually `"Y"`) |

### `b4c_request_driver_licence.csv`

One row per licence appearance.

| Column | Notes |
|---|---|
| `driver_license_id` | Monotonic identifier |
| `licencenumber` | Matching field — UK driving licence format, may be mutated |
| `licencetype` | Usually `"FULL_UK"` |
| `licencestartdate` | DOB + 17 years + random offset |

### `b4c_request_driver_address.csv`

One row per address appearance.

| Column | Notes |
|---|---|
| `driver_address_id` | Monotonic identifier |
| `line1`, `line2`, `town`, `county`, `postcode` | UK address components |
| `housenumber` | Numeric/alphanumeric building number |

### `ground_truth.csv` (optional)

Debugging sidecar with one row per appearance:

| Column | Description |
|---|---|
| `correlationid` | Links back to all four tables |
| `driver_id` | Links to `b4c_request_driver` |
| `base_person_id` | Canonical identity (ground truth) |
| `applied_noise_firstname`, `applied_noise_surname`, `applied_noise_dob`, `applied_noise_dl` | `ErrorType` enum value or `None` if clean |
| `dl_mutation_class` | `"benign_suffix"`, `"other"`, or `None` — indicates if DL mutation preserved PK |

## Testing

The project includes 59 tests covering all layers:

```bash
# Run full suite
pytest

# Run with coverage
pytest --cov=person_matching_synth

# Run specific test module
pytest tests/test_noise.py
```

### Test Structure

| Module | Tests | Coverage |
|---|---|---|
| `test_config.py` | 12 | Config validation, weight structure |
| `test_noise.py` | 14 | All noise functions (typo, transposition, etc.) |
| `test_base_person.py` | 6 | Pool generation, PK/SK computation, SK collisions |
| `test_appearance.py` | 10 | Invariant verification, appearance building, retry logic |
| `test_generate.py` | 5 | End-to-end integration (file creation, row counts, columns) |

All tests are deterministic and pass with the default seed (42).

## Project Structure

```
tadpole/
├── person_matching_synth/
│   ├── __init__.py          # Public API re-exports
│   ├── config.py            # ErrorType, FIELD_WHITELIST, GeneratorConfig
│   ├── noise.py             # 8 pure noise functions + NOISE_DISPATCH
│   ├── fields.py            # mutate_field, mutate_dl dispatchers
│   ├── base_person.py       # BasePerson, Address, compute_pk, compute_sk, generate_base_pool
│   ├── appearance.py        # QuoteAppearance, IdCounters, build_appearance, verify_invariant
│   ├── emit.py              # write_tables CSV streaming
│   └── generate.py          # CLI entry point (main) and generate() orchestrator
├── tests/
│   ├── conftest.py          # Shared Faker/RNG fixtures
│   ├── test_config.py
│   ├── test_noise.py
│   ├── test_base_person.py
│   ├── test_appearance.py
│   └── test_generate.py
├── synth_out/               # Generated output (gitignored)
│   ├── b4c_request_quote.csv
│   ├── b4c_request_driver.csv
│   ├── b4c_request_driver_licence.csv
│   ├── b4c_request_driver_address.csv
│   └── ground_truth.csv
├── pyproject.toml           # Project metadata, dependencies, entry point
├── person_matching_synthetic_data_spec.md  # Original specification
├── IMPLEMENTATION_COMPLETE.md  # Implementation summary
└── README.md               # This file
```

## Matching Algorithm Contract

The generator is designed to test a person-matching algorithm with the following contract:

### Input

Four tables (joined on `correlationid` and `driver_id` where applicable), each containing one or more appearances of a base person with potentially noisy PII.

### Matching Logic (Expected)

For each appearance, the algorithm should attempt to recover the canonical base person ID:

1. **Primary Key attempt**: Compute `pk_obs = UPPER(TRIM(licencenumber))[0:-2]`. If `pk_obs` equals a known `pk_truth` from the ground truth, match found.
2. **Secondary Key fallback**: If PK fails or is unavailable (DL blanked), compute `sk_obs = first_initial + UPPER(TRIM(surname)) + YYYYMMDD(dob)`. If `sk_obs` equals a known `sk_truth`, match found.
3. **No match**: If both fail, the appearance is unrecoverable.

### Invariant

The generator enforces: **Every appearance must be recoverable via PK or SK** (unless `allow_unrecoverable_appearances=True`). This guarantees the test data is solvable.

### Edge Cases Covered

- **DL absent**: When `dl_presence_rate` omits a licence, PK is impossible; SK must succeed
- **SK collisions**: Multiple base persons with identical SK but different DLs — algorithm must disambiguate via PK when DL present
- **Benign suffix mutations**: DL mutations that only affect the last two characters preserve PK (since PK strips last two chars)
- **Blanked fields**: `firstname`, `surname`, `dob`, or `licencenumber` may be replaced with empty string, forcing reliance on the other key

## Development

### Adding New Error Types

1. Add the `ErrorType` member in `config.py`
2. Extend `FIELD_WHITELIST` in both `config.py` and `fields.py` to include the new type for relevant fields
3. Implement the pure mutation function in `noise.py`
4. Register it in `NOISE_DISPATCH` in `fields.py`
5. Add unit tests in `tests/test_noise.py`

### Extending Output Schema

To add columns to any output table:

1. Update the `*_COLUMNS` list in `emit.py`
2. Extend the corresponding row-building logic in `appearance.py` (`build_appearance()`)
3. Update `ground_truth.csv` column list if debugging data is needed
4. Add integration test coverage in `tests/test_generate.py`

### Reproducibility

All randomness is controlled via two RNGs:

- `random.Random(seed)` — used for all integer/boolean decisions and UUID generation
- `Faker.seed_instance(seed)` — used for name/address/DOB generation

Setting the same `seed` in `GeneratorConfig` produces byte-identical output across runs and platforms (Python version permitting).

## License

[Specify license here]

## References

- Original specification: `person_matching_synthetic_data_spec.md`
- Implementation summary: `IMPLEMENTATION_COMPLETE.md`
- Matching algorithm spec: `person_matching.docx` (external)
