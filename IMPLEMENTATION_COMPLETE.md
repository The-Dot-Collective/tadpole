# Person-Matching Synthetic Data Generator — Implementation Complete

## Summary

The `person_matching_synth` package has been fully implemented according to the specification in `person_matching_synthetic_data_spec.md`. The generator produces configurable synthetic quote data across four CSV tables for validating the deterministic Person-matching algorithm.

## Project Structure

```
tadpole/
├── person_matching_synth/
│   ├── __init__.py          # Public API re-exports
│   ├── config.py            # ErrorType, FIELD_WHITELIST, GeneratorConfig with validation
│   ├── noise.py             # 8 pure noise functions + NOISE_DISPATCH
│   ├── fields.py            # mutate_field, mutate_dl dispatchers
│   ├── base_person.py       # BasePerson, Address, compute_pk, compute_sk, generate_base_pool
│   ├── appearance.py        # QuoteAppearance, IdCounters, build_appearance, verify_invariant
│   ├── emit.py              # write_tables CSV streaming
│   └── generate.py          # CLI entry point (main) and generate() orchestrator
├── tests/
│   ├── conftest.py          # Shared faker/rng fixtures
│   ├── test_config.py       # 12 validation tests
│   ├── test_noise.py        # 14 noise function tests
│   ├── test_base_person.py  # 6 pool generation tests
│   ├── test_appearance.py   # 10 invariant & appearance tests
│   └── test_generate.py     # 5 integration tests
├── pyproject.toml           # Project metadata, deps, entry point
└── person_matching_synthetic_data_spec.md  # Original specification
```

## Key Features Implemented

- **Base person pool** with configurable DL presence rate and SK collision pairs
- **UK-locale Faker** integration (en_GB) for realistic names, addresses, DOB
- **Field-specific noise model** per §4.2 whitelist with weighted sampling
- **DL mutation logic** distinguishing benign suffix (PK-preserving) vs destructive
- **Matchability invariant** (§3.3) enforced with retry loop; `verify_invariant()` public hook
- **Deterministic UUIDs** via RNG-seeded generator for reproducible correlation IDs
- **Streaming CSV output** matching DDL column order exactly
- **Ground truth sidecar** with per-appearance noise labels and DL mutation class
- **Full CLI** exposing all 14 `GeneratorConfig` parameters

## Verification

```bash
# Run full test suite
pytest tests/ -v
# Result: 59 passed in 0.68s

# Generate sample data
python -m person_matching_synth.generate \
  --seed 42 \
  --n-persons 3 \
  --quotes-per-person-min 2 \
  --quotes-per-person-max 2 \
  --error-rate 0.5 \
  --output-dir ./synth_out

# Output: 5 CSV files (4 tables + ground_truth.csv)
```

## Design Decisions

- **Python ≥ 3.11** for native union syntax (`str | None`) and `Literal`
- **`random.Random`** (not numpy) for RNG as specified; Faker seeded separately
- **No circular imports** — `FIELD_WHITELIST` lives in `config.py`; `fields.py` imports it
- **ErrorType serialization** — `.value` used in ground truth CSV (not Python repr)
- **`verify_invariant`** re-exported from `__init__.py` for external test harness use

## Out of Scope (as per spec)

- Vehicle matching (`b4c_request_car`)
- Address entity resolution
- UPRN or PolicyCenter tables
- Temporal dynamics (name/address changes over time)
- ML-based synthesis
