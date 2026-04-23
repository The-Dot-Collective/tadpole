"""Top-level generation orchestrator and CLI entry point."""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
import random

from faker import Faker

from .config import GeneratorConfig, default_weights
from .base_person import generate_base_pool, compute_pk, compute_sk
from .appearance import IdCounters, build_appearance, InvariantViolation
from .emit import write_tables


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
    # Seed RNGs
    rng = random.Random(config.seed)
    faker = Faker(config.locale)
    faker.seed_instance(config.seed)

    # Generate base person pool
    base_pool = generate_base_pool(config, faker, rng)

    # Create a fresh IdCounters for this run
    id_counters = IdCounters()

    # Stream appearances directly to emit to avoid holding all in memory
    def appearance_stream():
        for person in base_pool:
            n_appearances = rng.randint(config.quotes_per_person_min, config.quotes_per_person_max)
            for _ in range(n_appearances):
                try:
                    app = build_appearance(person, 0, id_counters, config, faker, rng)
                    yield app
                except InvariantViolation as e:
                    if not config.allow_unrecoverable_appearances:
                        raise
                    # If unrecoverable appearances are allowed, we still emit something?
                    # The spec says "deliberately produce ground-truth negatives".
                    # For now, re-raise if not allowed; if allowed, we could emit a placeholder.
                    # But the invariant check in build_appearance already respects allow_unrecoverable_appearances,
                    # so it will not raise when that flag is True. So this except is unreachable when flag=True.
                    raise

    paths = write_tables(appearance_stream(), config)
    return paths


def main() -> None:
    """CLI entry point. Argparse surfacing every GeneratorConfig field."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic quote data for person-matching algorithm validation."
    )
    # Numeric / rate parameters
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--n-persons", type=int, default=1000, help="Number of base persons (default: 1000)")
    parser.add_argument("--quotes-per-person-min", type=int, default=1, help="Min quotes per person (default: 1)")
    parser.add_argument("--quotes-per-person-max", type=int, default=8, help="Max quotes per person (default: 8)")
    parser.add_argument("--error-rate", type=float, default=0.15, help="Per-field mutation probability [0-1] (default: 0.15)")
    parser.add_argument("--dl-presence-rate", type=float, default=0.95, help="Probability a person has a driving licence [0-1] (default: 0.95)")
    parser.add_argument("--dl-benign-suffix-mutation-rate", type=float, default=0.10, help="Probability of benign DL suffix mutation [0-1] (default: 0.10)")
    parser.add_argument("--sk-collision-rate", type=float, default=0.01, help="Probability of SK collision pair creation [0-1] (default: 0.01)")
    parser.add_argument("--max-errors-per-appearance", type=int, default=2, help="Cap on simultaneous field mutations (default: 2)")
    parser.add_argument("--locale", type=str, default="en_GB", help="Faker locale (default: en_GB)")
    parser.add_argument("--output-dir", type=str, default="./synth_out", help="Output directory (default: ./synth_out)")
    parser.add_argument("--no-ground-truth", action="store_true", help="Do not emit ground_truth.csv")

    args = parser.parse_args()

    # Build config
    config = GeneratorConfig(
        seed=args.seed,
        n_persons=args.n_persons,
        quotes_per_person_min=args.quotes_per_person_min,
        quotes_per_person_max=args.quotes_per_person_max,
        error_rate=args.error_rate,
        dl_presence_rate=args.dl_presence_rate,
        dl_benign_suffix_mutation_rate=args.dl_benign_suffix_mutation_rate,
        sk_collision_rate=args.sk_collision_rate,
        max_errors_per_appearance=args.max_errors_per_appearance,
        allow_unrecoverable_appearances=False,
        locale=args.locale,
        output_dir=Path(args.output_dir),
        emit_ground_truth=not args.no_ground_truth,
    )

    print(f"Generating synthetic data with seed={config.seed}, n_persons={config.n_persons} ...")
    start = datetime.now()
    paths = generate(config)
    elapsed = datetime.now() - start
    print(f"Done in {elapsed.total_seconds():.2f}s. Output files:")
    for name, path in paths.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
