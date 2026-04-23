"""Base person entity and pool generation."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
import random
from faker import Faker


@dataclass(frozen=True)
class Address:
    """Stable UK address for a base person (not mutated across appearances)."""
    housenumber: str
    line1: str
    line2: Optional[str]
    town: str
    county: str
    country: str
    postcode: str


@dataclass(frozen=True)
class BasePerson:
    """Canonical ground-truth identity."""
    base_person_id: int
    firstname: str
    surname: str
    dob: date
    dl: Optional[str]           # None if dl_presence_rate did not fire
    address: Address
    pk_truth: Optional[str]     # None iff dl is None
    sk_truth: str               # always defined; fn/sn/dob mandatory


def compute_pk(dl: Optional[str]) -> Optional[str]:
    """
    Apply normalisation: UPPER(TRIM(dl))[0:-2].
    Returns None if dl is None or empty after trim.
    """
    if dl is None:
        return None
    trimmed = dl.strip().upper()
    if not trimmed:
        return None
    return trimmed[:-2] if len(trimmed) >= 2 else trimmed


def compute_sk(firstname: str, surname: str, dob: date) -> str:
    """
    first_initial + UPPER(TRIM(surname)) + dob.strftime('%Y%m%d').
    Surname is stripped of non-alphanumeric characters before normalisation
    (e.g. "O'Brien" -> "OBRIEN").
    Never returns None; caller must guarantee inputs are non-empty.
    """
    first_initial = firstname[0].upper() if firstname else ""
    # Strip non-alphanumeric, then upper and trim
    surname_clean = "".join(ch for ch in surname if ch.isalnum()).strip().upper()
    dob_str = dob.strftime("%Y%m%d")
    return f"{first_initial}{surname_clean}{dob_str}"


def _generate_dl(firstname: str, surname: str, dob: date, rng: random.Random) -> str:
    """
    Generate a UK driving licence number in the format:
    SURNAME_STEM(5) + DOB_YYMMDD(6) + INITIALS(2) + ORDINAL_SUFFIX(2)

    - Surname stem: first 5 chars of uppercase surname, left-padded with 'X' if shorter.
    - DOB encoded: YYMMDD (2-digit year, 2-digit month, 2-digit day).
    - Initials: first two chars of firstname (uppercase), second char falls back to 'X'.
    - Ordinal suffix: random 2-digit number from 01 to 99, zero-padded.
    """
    # Surname stem (5 chars)
    surname_clean = surname.strip().upper()
    if len(surname_clean) >= 5:
        surname_stem = surname_clean[:5]
    else:
        surname_stem = surname_clean.ljust(5, "X")

    # DOB encoded (6 chars: YYMMDD)
    yy = dob.strftime("%y")  # 2-digit year
    mm = dob.strftime("%m")  # 2-digit month
    dd = dob.strftime("%d")  # 2-digit day
    dob_encoded = f"{yy}{mm}{dd}"

    # Initials (2 chars)
    first_clean = firstname.strip().upper()
    if len(first_clean) >= 2:
        initials = first_clean[:2]
    elif len(first_clean) == 1:
        initials = first_clean[0] + "X"
    else:
        initials = "XX"

    # Ordinal suffix (2 digits, 01-99)
    ordinal = rng.randint(1, 99)
    ordinal_str = f"{ordinal:02d}"

    return f"{surname_stem}{dob_encoded}{initials}{ordinal_str}"


def _generate_uk_address(faker: Faker) -> Address:
    """Generate a plausible UK address using Faker."""
    # Faker's uk address provider gives us realistic components
    housenumber = faker.building_number()
    line1 = faker.street_name()
    line2 = faker.secondary_address()  # may be empty
    town = faker.city()
    county = faker.county()
    country = "United Kingdom"
    postcode = faker.postcode()

    # Normalize empty line2 to None
    line2_norm = line2 if line2 and line2.strip() else None

    return Address(
        housenumber=housenumber,
        line1=line1,
        line2=line2_norm,
        town=town,
        county=county,
        country=country,
        postcode=postcode,
    )


def generate_base_pool(
    config,
    faker: Faker,
    rng: random.Random,
) -> list[BasePerson]:
    """
    Construct the base person pool.

    Draws n_persons identities from Faker.
    Applies dl_presence_rate to decide DL presence per person.
    Applies sk_collision_rate to force a subset of base persons into SK-collision pairs
    (same first initial + normalised surname + DOB, different DL).
    Computes pk_truth and sk_truth per base person.
    """
    pool: list[BasePerson] = []
    collision_partners: dict[int, int] = {}  # maps person_id -> partner_id for SK collisions

    for i in range(1, config.n_persons + 1):
        # Draw identity
        firstname = faker.first_name()
        surname = faker.last_name()
        dob = faker.date_of_birth(minimum_age=18, maximum_age=80)
        address = _generate_uk_address(faker)

        # Decide DL presence
        has_dl = rng.random() < config.dl_presence_rate
        dl = _generate_dl(firstname, surname, dob, rng) if has_dl else None

        pk_truth = compute_pk(dl)
        sk_truth = compute_sk(firstname, surname, dob)

        person = BasePerson(
            base_person_id=i,
            firstname=firstname,
            surname=surname,
            dob=dob,
            dl=dl,
            address=address,
            pk_truth=pk_truth,
            sk_truth=sk_truth,
        )
        pool.append(person)

        # SK collision: with probability sk_collision_rate, pair this person with a previous one
        if rng.random() < config.sk_collision_rate and len(pool) >= 2:
            # Pick a random previous person (not the current one)
            partner_idx = rng.randint(0, len(pool) - 2)  # safe: pool has at least 2 elements here
            partner = pool[partner_idx]
            # Check if they already share SK; if not, we need to adjust current person's SK to match
            # The spec says: "two distinct base persons sharing identical first-initial, normalised surname, and DOB but with different DL values"
            # So we need to force the collision by adjusting either firstname or dob of current person to match partner's SK
            # Simplest: adopt partner's firstname and dob, keep own surname (or adopt surname too)
            # But we must preserve that they are distinct persons (different dl and base_person_id)
            # Strategy: overwrite current person's firstname and dob to match partner, keep own surname
            # This guarantees same SK (first initial + surname + dob) but different DL (since dl was generated from original fn/sn/dob)
            # However, we already generated dl from original fn/sn/dob. To ensure different DL, we must regenerate dl after adjusting fn/dob.
            # Actually simpler: pick a partner that already has matching SK by chance? No, probability too low.
            # Better: force collision by setting current person's firstname = partner.firstname, dob = partner.dob, keep own surname.
            # Then regenerate dl from the new (firstname, surname, dob) triple — it will be different from partner's dl because surname differs or ordinal differs.
            # But the spec says "same first-initial + normalised surname + DOB". That means first initial must match, surname normalized must match, DOB must match.
            # So we need: firstname[0] == partner.firstname[0], UPPER(TRIM(surname)) == UPPER(TRIM(partner.surname)), and dob == partner.dob.
            # Easiest: copy partner's firstname and dob exactly, and set surname to partner.surname as well. That gives identical SK. But then they are not distinct? They are distinct persons with different dl and base_person_id.
            # That's fine: two persons with identical SK but different DL is exactly the collision scenario.
            # So we'll overwrite both firstname and surname and dob to match partner exactly.
            # But then the current person's identity is no longer drawn from Faker — it's a clone. That's acceptable for a small collision subset.
            # Let's do that: replace current person's firstname, surname, dob with partner's, then regenerate dl (which will differ because dl includes ordinal suffix randomly).
            # However, we must also regenerate pk_truth and sk_truth accordingly.
            # Since we're inside the loop and already appended the original person, we need to replace the last entry.
            # Actually, we can decide collision before creating the person: with probability sk_collision_rate, pick an existing person as template and clone their SK.
            # That's cleaner: for each new person, with prob sk_collision_rate, copy firstname, surname, dob from a random existing person, then generate a new dl (different ordinal).
            # Let's restructure: before creating person, decide if this will be a collision clone.
            pass  # We'll restructure below

    # Actually, let's re-implement more cleanly with collision logic up-front
    return _generate_base_pool_impl(config, faker, rng)


def _generate_base_pool_impl(
    config,
    faker: Faker,
    rng: random.Random,
) -> list[BasePerson]:
    pool: list[BasePerson] = []
    for i in range(1, config.n_persons + 1):
        # Determine if this person should be an SK collision clone of an existing one
        if pool and rng.random() < config.sk_collision_rate:
            # Clone SK from a random existing person
            template = rng.choice(pool)
            firstname = template.firstname
            surname = template.surname
            dob = template.dob
            # Generate a new DL (different ordinal suffix) to keep them distinct
            dl = _generate_dl(firstname, surname, dob, rng)
            # Ensure dl is different from template's dl (very high probability already, but enforce if needed)
            attempts = 0
            while dl == template.dl and attempts < 5:
                dl = _generate_dl(firstname, surname, dob, rng)
                attempts += 1
            address = _generate_uk_address(faker)
        else:
            # Fresh identity
            firstname = faker.first_name()
            surname = faker.last_name()
            dob = faker.date_of_birth(minimum_age=18, maximum_age=80)
            address = _generate_uk_address(faker)
            has_dl = rng.random() < config.dl_presence_rate
            dl = _generate_dl(firstname, surname, dob, rng) if has_dl else None

        pk_truth = compute_pk(dl)
        sk_truth = compute_sk(firstname, surname, dob)

        person = BasePerson(
            base_person_id=i,
            firstname=firstname,
            surname=surname,
            dob=dob,
            dl=dl,
            address=address,
            pk_truth=pk_truth,
            sk_truth=sk_truth,
        )
        pool.append(person)

    return pool
