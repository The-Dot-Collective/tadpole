# Person-Matching Synthetic Data Generator — Implementation Specification

**Target:** GitHub Copilot-assisted implementation in Python. No further clarification from the analyst should be required.
**Purpose:** Produce configurable synthetic quote data for validating the deterministic Person-matching algorithm defined in `person_matching.docx`. The generator must produce realistic PII variance such that the same base person is matchable via either Primary Key (truncated DL) or Secondary Key (first-initial + surname + DOB) across clean and noisy appearances.

---

## 1. Library Evaluation and Selection

### 1.1 Candidate comparison

| Library | Fit for record linkage testing | Verdict |
|---|---|---|
| **Faker** | Produces realistic per-locale PII (UK names, postcodes, DOB, addresses) with a seedable RNG. No built-in mutation/corruption — must be hand-written. Full deterministic control of every field. | **Selected.** |
| **mimesis** | Similar PII breadth and faster than Faker, but UK-locale realism (postcodes, title, surname frequency) is weaker and its RNG ergonomics are less predictable across versions. | Rejected. |
| **SDV** (Synthetic Data Vault) | GAN/statistical model over a real source dataset. Requires representative training data — we do not have a cleansed ground-truth person table to train on, and the learned distribution would be opaque. Cannot guarantee same base-person recoverability across mutations because identity is not a first-class concept in the model. | Rejected. |
| **DataSynthesizer** | Bayesian network synthesis preserving correlations. Same objection as SDV: requires source data and does not expose deterministic identity threads. | Rejected. |
| **Gretel** | Commercial/SaaS generative models. Cost, external dependency, and black-box mutation make it unsuitable for a white-box algorithm test harness. | Rejected. |

### 1.2 Justification

Faker is selected because this task requires a **white-box, deterministic, identity-preserving generator**, not a statistical model. The matching algorithm under test is rule-based (truncated DL, SK composite), so the generator must be rule-based in mirror image: we need to construct a known base person, then emit multiple appearances of that base person with controlled, field-specific noise, while guaranteeing that at least one of PK or SK remains recoverable against the base entity. Generative libraries (SDV, DataSynthesizer, Gretel) optimise distributional fidelity, not identity preservation across records — the very property this test suite depends on. Faker supplies realistic UK-locale atoms (names, postcodes, DOB) with a seedable RNG; the identity-preservation layer and the error-injection layer are written on top. A secondary recommendation for future work is [Gecko](https://github.com/ul-mds/gecko), which is purpose-built for record-linkage test data with frequency-table-driven generation and vectorised mutation; it is not used here to keep the implementation self-contained and to avoid a non-PyPI data dependency (Gecko requires cloning the `gecko-data` repo for UK frequency tables, which we do not yet have).

---

## 2. Scope and Field Inventory

The generator emits synthetic rows that shadow the production schemas involved in the Person-matching algorithm. Fields are derived from `person_matching.docx` and the four SQL DDL files: `b4c_request_quote.sql`, `b4c_request_driver.sql`, `b4c_request_driver_licence.sql`, `b4c_request_driver_address.sql`. Non-matching fields (payment frequency, voluntary excess, partitioning columns) are populated with plausible defaults but are not part of the noise model.

### 2.1 Fields required by the matching algorithm

Per `person_matching.docx` the algorithm consumes four attributes per Person record:

| Attribute | Symbol | Source table | Source column |
|---|---|---|---|
| Driving licence number | `dl(q)` | `b4c_request_driver_licence` | `licencenumber` |
| First name | `fn(q)` | `b4c_request_driver` | `firstname` |
| Surname | `sn(q)` | `b4c_request_driver` | `surname` |
| Date of birth | `dob(q)` | `b4c_request_driver` | `dateofbirth` |

The algorithm also requires a quote key. Per standing project context, a unique Quote is the composite of `correlationid` + `id`. Across the tables this surfaces as:

| Key | Tables carrying it |
|---|---|
| `correlationid` (VARCHAR) | all four |
| `quote_header_id` (VARCHAR) | all four |
| `driver_id` (BIGINT) | `b4c_request_driver`, `b4c_request_driver_licence`, `b4c_request_driver_address` |
| `id` (BIGINT) | `b4c_request_quote` |

### 2.2 Full field inventory per table

Fields marked **matching** participate in the noise model. Fields marked **context** are populated but not mutated. Fields marked **key** are generated deterministically from the quote/driver identity.

#### `b4c_request_quote`
| Field | Type | Role | Generation rule |
|---|---|---|---|
| `id` | BIGINT | key | Monotonic counter, unique per row |
| `quote_header_id` | VARCHAR | key | UUID4 string |
| `correlationid` | VARCHAR | key | UUID4 string, shared across all four tables for one quote |
| `brand` | VARCHAR | context | Sample from `{"BRAND_A", "BRAND_B", "BRAND_C"}` |
| `source_timestamp` | TIMESTAMP | context | `quote_datetime` |
| `shredding_timestamp` | TIMESTAMP | context | `quote_datetime + 1 day` |
| `pcwrefid`, `protectnoclaims`, `startdate`, `coverlevel`, `paymentfrequency`, `voluntaryexcess`, `source`, `channel`, `line`, `offering`, `refids` | VARCHAR | context | Plausible fixed/sampled defaults |
| `dal_year`, `dal_month`, `dal_day` | VARCHAR | context | Derived from `quote_datetime` |

#### `b4c_request_driver`
| Field | Type | Role | Generation rule |
|---|---|---|---|
| `quote_header_id`, `correlationid` | VARCHAR | key | Inherited from quote |
| `driver_id` | BIGINT | key | Monotonic counter, unique per person-appearance |
| `pcr_drvid` | VARCHAR | context | `"DRV-" + str(driver_id)` |
| `firstname` | VARCHAR | **matching** | Base person `firstname`, optionally mutated |
| `middlename` | VARCHAR | context | Fixed NULL for now |
| `surname` | VARCHAR | **matching** | Base person `surname`, optionally mutated |
| `dateofbirth` | TIMESTAMP | **matching** | Base person `dob`, optionally mutated |
| `title` | VARCHAR | context | `"MR"`, `"MRS"`, `"MS"`, `"DR"` sampled |
| `gender` | VARCHAR | context | `"M"` / `"F"` |
| `maritalstatus`, `residencesince`, `employmentstatus`, `childrenunder16`, `carsinhousehold`, `ismaindriver`, `isproposer`, `relationshiptoproposer`, `ishomeowner`, `isncdowner`, `ncddurationyears`, `ncddurationmonths`, `wasrefusedinsurancebefore`, `othervehicleuse`, `startdate`, `quote_entry_time` | VARCHAR / TIMESTAMP | context | Plausible defaults, not mutated |
| `source_timestamp`, `shredding_timestamp` | TIMESTAMP | context | As per quote |
| `partition_0`, `dal_year`, `dal_month`, `dal_day` | VARCHAR | context | Derived |

#### `b4c_request_driver_licence`
| Field | Type | Role | Generation rule |
|---|---|---|---|
| `quote_header_id`, `correlationid` | VARCHAR | key | Inherited from quote |
| `driver_license_id` | BIGINT | key | Monotonic counter |
| `pcr_drvid`, `driver_id` | VARCHAR / BIGINT | key | Inherited from driver |
| `licencenumber` | VARCHAR | **matching** | Base person `dl`, optionally mutated or blanked |
| `licencetype` | VARCHAR | context | `"FULL_UK"` |
| `licencestartdate` | VARCHAR | context | DOB + 17y + random offset |
| `licencestatus` | VARCHAR | context | `"VALID"` |
| `medicalconditions` | VARCHAR | context | `"NONE"` |
| `licenceheldyears` | VARCHAR | context | Derived from `licencestartdate` and `quote_datetime` |
| `source_timestamp`, `shredding_timestamp`, `dal_year`, `dal_month`, `dal_day` | — | context | As per quote |

#### `b4c_request_driver_address`
| Field | Type | Role | Generation rule |
|---|---|---|---|
| `quote_header_id`, `correlationid` | VARCHAR | key | Inherited from quote |
| `driver_address_id` | BIGINT | key | Monotonic counter |
| `pcr_drvid`, `driver_id` | — | key | Inherited from driver |
| `housenumber`, `line1`, `line2`, `line3`, `line4`, `town`, `county`, `country`, `postcode` | VARCHAR | context | Plausible UK address, stable per base person (address is not in the Person-matching algorithm and is NOT mutated by this generator) |
| `source_timestamp`, `shredding_timestamp`, `dal_year`, `dal_month`, `dal_day` | — | context | As per quote |

**Note on scope:** this generator targets **Person** matching only. Vehicle (`b4c_request_car`) and Address entity matching are out of scope. Address fields are emitted for schema completeness but held stable per base person.

---

## 3. Entity Model

### 3.1 Base person

The generator first materialises a **pool of base persons**. Each base person is the canonical, ground-truth identity that later appears across multiple quote rows. The base person carries:

- A stable synthetic `base_person_id` (integer, used only for ground-truth evaluation — never written to the synthetic table output).
- Canonical values for `firstname`, `surname`, `dob`, and `dl` drawn once from Faker.
- A precomputed canonical `PK_truth = truncate(normalise(dl))` and `SK_truth = first_initial(firstname) + normalise(surname) + dob_yyyymmdd`, held for test-harness ground truth.
- Stable address fields (not matched on, but kept invariant for realism).

The canonical DL follows the UK format: 5-char surname stem + 6-digit DOB-encoded + 2-char initials + 2-char ordinal suffix. The algorithm truncates the final 2 characters, so the **last two characters of DL are the only DL subfield that may mutate without breaking PK matching**. This is important for the noise model (see §4.3).

### 3.2 Quote appearances

Each base person is emitted across a random number of **quote appearances** (bounded by `quotes_per_person_min` and `quotes_per_person_max`). Each appearance is a full row-set spanning the four tables, sharing one `correlationid` and one `quote_header_id`. Across appearances, the base person's canonical attributes are carried forward with optional, per-field noise applied.

### 3.3 Matchability invariant

For every quote appearance of a base person, **at least one** of the following must hold after mutation:

- `truncate(normalise(dl_observed)) == PK_truth`, **OR**
- `first_initial(firstname_observed) + normalise(surname_observed) + dob_observed_yyyymmdd == SK_truth`

This invariant is the generator's hard contract. It guarantees every appearance is recoverable against the base person by the algorithm under test. The generator MUST verify this invariant after each appearance is constructed and reject/regenerate if violated. A configuration option `allow_unrecoverable_appearances: bool = False` may be exposed to deliberately produce ground-truth negatives for precision testing.

### 3.4 Collisions and false-positive material

A separate, optional generation mode produces **SK collision pairs**: two distinct base persons sharing identical first-initial, normalised surname, and DOB but with different DL values. This exercises the transitivity break scenario called out in `person_matching.docx`. Controlled by `sk_collision_rate`.

---

## 4. Noise Model

Noise is **field-appropriate**, not random. Each field has a whitelist of applicable error types with per-type weights. Applying a type not in the field's whitelist is a generator bug.

### 4.1 Error types (enum)

```
TYPO            -- single-character substitution with a keyboard-adjacent character
TRANSPOSITION   -- swap two adjacent characters
ABBREVIATION    -- forename only: shorten to initial or common short form (e.g. "Robert" -> "Rob", "R")
MISSING_TOKEN   -- drop one whitespace-separated token (address lines, compound surnames)
BLANK           -- field set to empty string or NULL
DIGIT_SWAP      -- single digit substitution (postcodes, DOB components, DL numeric block)
CASE_FLIP       -- invert case of one or more characters
WHITESPACE      -- insert/strip leading or trailing whitespace
```

### 4.2 Field-to-error-type whitelist

| Field | Permitted error types | Rationale |
|---|---|---|
| `firstname` | `TYPO`, `TRANSPOSITION`, `ABBREVIATION`, `CASE_FLIP`, `BLANK` | Realistic data-entry variance for forenames. `ABBREVIATION` is the signature forename error. |
| `surname` | `TYPO`, `TRANSPOSITION`, `MISSING_TOKEN`, `CASE_FLIP`, `WHITESPACE`, `BLANK` | `MISSING_TOKEN` handles double-barrelled surnames. |
| `dateofbirth` | `DIGIT_SWAP`, `BLANK` | DOB is structured; only digit-level errors make sense. |
| `licencenumber` (DL) | `TYPO`, `TRANSPOSITION`, `DIGIT_SWAP`, `WHITESPACE`, `CASE_FLIP`, `BLANK` | `BLANK` forces SK fallback path. |
| `postcode` (address context) | `DIGIT_SWAP`, `WHITESPACE`, `CASE_FLIP` | Postcodes are structured; digit swap is the realistic error. Not matched on by Person algorithm — included for completeness. |
| `line1`, `line2` (address context) | `MISSING_TOKEN`, `TYPO`, `WHITESPACE` | Address lines lose tokens (e.g. "Flat 2A" dropped). Not matched on by Person algorithm. |

### 4.3 DL-specific rules

The final two characters of a UK DL are the ordinal suffix. The matching algorithm strips them. The generator therefore distinguishes:

- **Benign DL mutation**: mutating only the final two characters (simulating a renewed licence). PK_truth is preserved. Controlled by `dl_benign_suffix_mutation_rate`.
- **Destructive DL mutation**: mutating any of the first N-2 characters. PK_truth is broken. If this fires, the generator must guarantee SK_truth still holds, or the appearance violates §3.3.
- **DL blanking**: field emitted as NULL or empty. Forces pure SK match.

### 4.4 Per-appearance error budget

Per appearance, for each field in the whitelist, an error is injected with probability `error_rate`. Multiple fields may be independently mutated in the same appearance. An optional `max_errors_per_appearance` cap prevents pathological multi-corruption rows. The generator picks the specific error type for a field by weighted sample from that field's whitelist; weights are exposed as config.

---

## 5. Configurable Parameters

All parameters live in a single `GeneratorConfig` dataclass. Defaults shown are starting values; all are overridable.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `seed` | `int` | `42` | Passed to Faker and `random.Random` for full reproducibility. |
| `n_persons` | `int` | `1_000` | Size of base person pool. |
| `quotes_per_person_min` | `int` | `1` | Lower bound on appearances per base person. |
| `quotes_per_person_max` | `int` | `8` | Upper bound on appearances per base person. |
| `error_rate` | `float` in `[0.0, 1.0]` | `0.15` | Per-field, per-appearance probability of applying noise. |
| `error_type_weights` | `dict[field_name, dict[ErrorType, float]]` | See §4.2 | Per-field weighting over permitted error types. |
| `dl_presence_rate` | `float` in `[0.0, 1.0]` | `0.95` | Probability a base person has a DL at all. Those without force SK-only matching. |
| `dl_benign_suffix_mutation_rate` | `float` in `[0.0, 1.0]` | `0.10` | Probability a given appearance mutates only the DL ordinal suffix. |
| `sk_collision_rate` | `float` in `[0.0, 1.0]` | `0.01` | Probability of constructing an SK-collision pair between two distinct base persons. |
| `max_errors_per_appearance` | `int` | `2` | Cap on simultaneous field mutations. |
| `allow_unrecoverable_appearances` | `bool` | `False` | If `True`, appearances that violate §3.3 are emitted as ground-truth negatives. |
| `locale` | `str` | `"en_GB"` | Faker locale. |
| `output_dir` | `Path` | — | Destination directory for the four CSVs. |
| `emit_ground_truth` | `bool` | `True` | Write a sidecar `ground_truth.csv` mapping every `(correlationid, driver_id)` to its `base_person_id`. |

---

## 6. Package Layout

```
person_matching_synth/
├── __init__.py
├── config.py          -- GeneratorConfig dataclass, ErrorType enum
├── base_person.py     -- BasePerson dataclass, base-pool generation
├── noise.py           -- Error-injection functions, one per ErrorType
├── fields.py          -- Field-level mutation dispatch per §4.2 whitelist
├── appearance.py      -- Quote-appearance construction, §3.3 invariant check
├── emit.py            -- Write to the four CSVs + ground_truth.csv
└── generate.py        -- Top-level entry point
```

---

## 7. Class and Function Signatures

### 7.1 `config.py`

```python
class ErrorType(Enum):
    TYPO: str
    TRANSPOSITION: str
    ABBREVIATION: str
    MISSING_TOKEN: str
    BLANK: str
    DIGIT_SWAP: str
    CASE_FLIP: str
    WHITESPACE: str

@dataclass(frozen=True)
class GeneratorConfig:
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
        """Validate: 0 <= rates <= 1, min <= max, whitelist-weight keys match §4.2."""

def default_weights() -> dict[str, dict[ErrorType, float]]:
    """Return the per-field error-type weight table from §4.2."""
```

### 7.2 `base_person.py`

```python
@dataclass(frozen=True)
class BasePerson:
    base_person_id: int
    firstname: str
    surname: str
    dob: date
    dl: str | None            # None if dl_presence_rate did not fire
    address: Address          # frozen dataclass; not mutated across appearances
    pk_truth: str | None      # None iff dl is None
    sk_truth: str             # always defined; fn/sn/dob mandatory by §2.1

@dataclass(frozen=True)
class Address:
    housenumber: str
    line1: str
    line2: str | None
    town: str
    county: str
    country: str
    postcode: str

def generate_base_pool(config: GeneratorConfig, faker: Faker, rng: random.Random) -> list[BasePerson]:
    """
    Construct the base person pool.

    Draws n_persons identities from Faker.
    Applies dl_presence_rate to decide DL presence per person.
    Applies sk_collision_rate to force a subset of base persons into SK-collision pairs
    (same first initial + normalised surname + DOB, different DL).
    Computes pk_truth and sk_truth per base person.
    """

def compute_pk(dl: str | None) -> str | None:
    """Apply normalisation from person_matching.docx §Inputs: UPPER(TRIM(dl))[0:-2]. Returns None if dl is None or empty after trim."""

def compute_sk(firstname: str, surname: str, dob: date) -> str:
    """first_initial + UPPER(TRIM(surname)) + dob.strftime('%Y%m%d'). Never returns None; caller must guarantee inputs are non-empty."""
```

### 7.3 `noise.py`

One function per ErrorType. Each function is pure and takes `(value, rng) -> mutated_value`. No function touches any state other than its inputs.

```python
def apply_typo(value: str, rng: random.Random) -> str: ...
def apply_transposition(value: str, rng: random.Random) -> str: ...
def apply_abbreviation(value: str, rng: random.Random) -> str: ...
def apply_missing_token(value: str, rng: random.Random) -> str: ...
def apply_blank(value: str, rng: random.Random) -> str: ...
def apply_digit_swap(value: str, rng: random.Random) -> str: ...
def apply_case_flip(value: str, rng: random.Random) -> str: ...
def apply_whitespace(value: str, rng: random.Random) -> str: ...

NOISE_DISPATCH: dict[ErrorType, Callable[[str, random.Random], str]]
"""Maps each ErrorType to its implementation function."""
```

Contract for each: idempotent given the same `rng` state; never raises on empty input (returns empty); never silently no-ops when called — if the input makes the mutation meaningless (e.g. `TRANSPOSITION` on a single-char string), must raise `NoiseNotApplicable` so the caller can re-sample.

### 7.4 `fields.py`

```python
FIELD_WHITELIST: dict[str, list[ErrorType]]
"""Per-field permitted error types from §4.2."""

def mutate_field(
    field_name: str,
    value: str,
    config: GeneratorConfig,
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

    Raises if field_name is not in FIELD_WHITELIST.
    """

def mutate_dl(
    dl: str | None,
    config: GeneratorConfig,
    rng: random.Random,
) -> tuple[str | None, Literal["benign_suffix", "destructive", "blank", "none"]]:
    """
    DL-specific dispatcher. Implements §4.3.

    Returns the mutated DL and a tag indicating which mutation class fired.
    The tag drives the §3.3 invariant check.
    """
```

### 7.5 `appearance.py`

```python
@dataclass
class QuoteAppearance:
    correlationid: str
    quote_header_id: str
    id: int                       # b4c_request_quote.id
    driver_id: int
    driver_license_id: int
    driver_address_id: int
    base_person_id: int           # ground truth; not written to synthetic tables

    firstname_observed: str
    surname_observed: str
    dob_observed: date | None
    dl_observed: str | None

    applied_noise: dict[str, ErrorType | str | None]
    """Map of field_name -> ErrorType (or DL tag) for debugging and ground truth enrichment."""

    quote_row: dict           # ready for b4c_request_quote DDL
    driver_row: dict          # ready for b4c_request_driver DDL
    licence_row: dict         # ready for b4c_request_driver_licence DDL
    address_row: dict         # ready for b4c_request_driver_address DDL

def build_appearance(
    base_person: BasePerson,
    appearance_index: int,
    id_counters: IdCounters,
    config: GeneratorConfig,
    faker: Faker,
    rng: random.Random,
) -> QuoteAppearance:
    """
    Construct one appearance of base_person.

    Applies per-field mutation via mutate_field / mutate_dl.
    Enforces §3.3 matchability invariant:
        if post-mutation PK_observed != base_person.pk_truth
        AND SK_observed != base_person.sk_truth
        AND not config.allow_unrecoverable_appearances:
            retry with fresh rng draws up to MAX_RETRIES
            if still violated, raise InvariantViolation.
    Populates all four *_row dicts including all context fields.
    """

@dataclass
class IdCounters:
    """Monotonic id allocators, seeded fresh per run for reproducibility."""
    next_quote_id: int
    next_driver_id: int
    next_licence_id: int
    next_address_id: int
```

### 7.6 `emit.py`

```python
def write_tables(
    appearances: Iterable[QuoteAppearance],
    config: GeneratorConfig,
) -> dict[str, Path]:
    """
    Stream appearances to four CSVs under config.output_dir, matching the DDL column
    order of b4c_request_quote, b4c_request_driver, b4c_request_driver_licence,
    b4c_request_driver_address exactly.

    If config.emit_ground_truth, also writes ground_truth.csv with columns:
        correlationid, driver_id, base_person_id,
        applied_noise_firstname, applied_noise_surname, applied_noise_dob,
        applied_noise_dl, dl_mutation_class

    Returns a dict mapping logical table name -> output path.
    """
```

### 7.7 `generate.py`

```python
def generate(config: GeneratorConfig) -> dict[str, Path]:
    """
    Top-level orchestrator.

    1. Seed Faker(config.locale) and random.Random with config.seed.
    2. base_pool = generate_base_pool(...)
    3. For each base_person, draw n_appearances from
       uniform(quotes_per_person_min, quotes_per_person_max).
    4. For each appearance, call build_appearance(...).
    5. Pass the full iterable to write_tables(...).
    6. Return the paths dict.
    """

def main() -> None:
    """CLI entry point. Argparse surfacing every GeneratorConfig field."""
```

---

## 8. Parameter Contracts

- `seed`: any int; identical seeds with identical config produce byte-identical output.
- `n_persons`: `>= 1`.
- `quotes_per_person_min` / `_max`: `1 <= min <= max`.
- `error_rate`, `dl_presence_rate`, `dl_benign_suffix_mutation_rate`, `sk_collision_rate`: each in `[0.0, 1.0]`.
- `error_type_weights`: keys must be a subset of `FIELD_WHITELIST` keys. For each field present, its inner dict keys must be a subset of `FIELD_WHITELIST[field_name]`. Weights must be non-negative and sum to > 0 per field.
- `max_errors_per_appearance`: `>= 0`. `0` disables mutation.
- `output_dir`: must be writable; created if absent.
- Validation happens in `GeneratorConfig.__post_init__`. Invalid config raises `ValueError` before any generation begins.

---

## 9. Example Output Rows

Given `seed=42`, `n_persons=3`, `quotes_per_person_min=2`, `quotes_per_person_max=2`, `error_rate=0.5`, `allow_unrecoverable_appearances=False`.

### Base person (ground truth, not written to main tables)
```
base_person_id: 1
firstname:      "Robert"
surname:        "O'Brien"
dob:            1985-03-14
dl:             "OBRIE853146RO01"
pk_truth:       "OBRIE853146RO"
sk_truth:       "ROBRIEN19850314"
```

### Appearance 1 (clean)

`b4c_request_quote` row:
```
id: 1
quote_header_id: "b2c7e0f8-..."
correlationid:   "e9a11a4f-..."
brand:           "BRAND_A"
source_timestamp: 2024-05-14 09:12:03
...
```

`b4c_request_driver` row:
```
quote_header_id: "b2c7e0f8-..."
correlationid:   "e9a11a4f-..."
driver_id:       1
firstname:       "Robert"
surname:         "O'Brien"
dateofbirth:     1985-03-14 00:00:00
...
```

`b4c_request_driver_licence` row:
```
quote_header_id: "b2c7e0f8-..."
correlationid:   "e9a11a4f-..."
driver_id:       1
licencenumber:   "OBRIE853146RO01"
...
```

### Appearance 2 (forename abbreviation + DL benign suffix mutation)

`b4c_request_driver` row:
```
driver_id:       2
firstname:       "Rob"                    -- ABBREVIATION applied
surname:         "O'Brien"
dateofbirth:     1985-03-14 00:00:00
```

`b4c_request_driver_licence` row:
```
driver_id:       2
licencenumber:   "OBRIE853146RO02"        -- benign_suffix mutation, PK_truth preserved
```

Matching outcome: **Primary_match** via preserved truncated DL. SK also matches (first initial "R" + "OBRIEN" + "19850314") — a Primary_match with SK divergence flag would fire if the forename abbreviation changed the first initial. Here it does not.

### `ground_truth.csv` row for appearance 2
```
correlationid:             "f22b9c01-..."
driver_id:                 2
base_person_id:            1
applied_noise_firstname:   "ABBREVIATION"
applied_noise_surname:     null
applied_noise_dob:         null
applied_noise_dl:          null
dl_mutation_class:         "benign_suffix"
```

### Appearance where DL is blanked — forces SK fallback
```
firstname:      "Robert"
surname:        "O'Brien"
dateofbirth:    1985-03-14 00:00:00
licencenumber:  NULL                       -- BLANK applied
```
Matching outcome: SK path fires. `SK_observed == SK_truth` so **Secondary_match** is asserted against appearance 1.

### Appearance with destructive DL mutation + typo in surname — still recoverable via SK
```
firstname:      "Robert"
surname:        "O'Brien"                  -- unchanged
dateofbirth:    1985-03-14 00:00:00        -- unchanged
licencenumber:  "OBRIE853146RX01"          -- TYPO in position 12, PK_truth broken
```
Post-mutation: PK_observed = `"OBRIE853146RX"` ≠ PK_truth. SK_observed = `"ROBRIEN19850314"` = SK_truth. Invariant §3.3 holds. Matching outcome: **Secondary_match** (since q1 had PK and this one has PK but PKs differ, the algorithm suppresses SK fallback per Rule 2 — this is a **no_match** in the algorithm's classification, which is the correct, desired test signal for a corrupted DL that looks superficially valid). The ground truth file records `applied_noise_dl: "TYPO"`, `dl_mutation_class: "destructive"`, enabling the test harness to confirm the algorithm produced a ground-truth false negative and to quantify the false-negative rate contribution of destructive DL mutations.

---

## 10. Testing Hooks

The generator MUST expose a pure function:

```python
def verify_invariant(base_person: BasePerson, appearance: QuoteAppearance) -> bool:
    """True iff at least one of PK or SK recovers base_person from the observed fields."""
```

This is called internally during generation (§3.3) and must also be importable by the algorithm-under-test's test suite for post-hoc verification of emitted data. The ground-truth CSV alone is sufficient for precision/recall scoring of the matching algorithm; `verify_invariant` is the sanity check that the generator itself is correct.

---

## 11. Out of Scope

- Vehicle matching data (`b4c_request_car`).
- Address entity resolution (addresses are stable per base person, not a matching target here).
- UPRN or any PolicyCenter-side tables. Per `UPRN_facts.docx`, UPRN is not a Person-matching key.
- Probabilistic or ML-based synthesis. This generator is deterministic and white-box by design.
- Temporal dynamics (address changes, name changes at marriage). Out of scope for v1; the base person is temporally invariant across all appearances.
