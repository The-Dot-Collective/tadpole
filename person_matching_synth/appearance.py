"""Quote appearance construction, invariant enforcement, and row population."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, Literal
import random

from faker import Faker

from .config import ErrorType, GeneratorConfig
from .base_person import BasePerson, Address, compute_pk, compute_sk
from .fields import mutate_field, mutate_dl
from .noise import NoiseNotApplicable


def _deterministic_uuid4(rng: random.Random) -> str:
    """Generate a deterministic UUID4-like string using the provided RNG."""
    # UUID4 has 128 bits: 4 bits for version (0100), 2 bits for variant (10), rest random
    # We'll generate 16 random bytes and set the appropriate bits
    bytes_arr = bytearray(rng.getrandbits(8) for _ in range(16))
    # Set version to 4 (0100) in time_hi_and_version field (bytes 6 & 7, bits 4-7 of byte 6)
    bytes_arr[6] = (bytes_arr[6] & 0x0F) | 0x40  # 0100 xxxx
    # Set variant to RFC 4122 (10xx) in byte 8
    bytes_arr[8] = (bytes_arr[8] & 0x3F) | 0x80  # 10xx xxxx
    # Format as UUID string
    import uuid
    return str(uuid.UUID(bytes=bytes(bytes_arr)))


@dataclass
class IdCounters:
    """Monotonic id allocators, seeded fresh per run for reproducibility."""
    next_quote_id: int = 1
    next_driver_id: int = 1
    next_licence_id: int = 1
    next_address_id: int = 1

    def next_quote(self) -> int:
        val = self.next_quote_id
        self.next_quote_id += 1
        return val

    def next_driver(self) -> int:
        val = self.next_driver_id
        self.next_driver_id += 1
        return val

    def next_licence(self) -> int:
        val = self.next_licence_id
        self.next_licence_id += 1
        return val

    def next_address(self) -> int:
        val = self.next_address_id
        self.next_address_id += 1
        return val


@dataclass
class QuoteAppearance:
    """One appearance of a base person across the four tables."""
    correlationid: str
    quote_header_id: str
    id: int                       # b4c_request_quote.id
    driver_id: int
    driver_license_id: int
    driver_address_id: int
    base_person_id: int           # ground truth; not written to synthetic tables

    firstname_observed: str
    surname_observed: str
    dob_observed: Optional[date]  # None if blanked
    dl_observed: Optional[str]    # None if blanked

    applied_noise: dict[str, ErrorType | str | None]
    """Map of field_name -> ErrorType (or DL tag) for debugging and ground truth enrichment."""

    quote_row: dict           # ready for b4c_request_quote DDL
    driver_row: dict          # ready for b4c_request_driver DDL
    licence_row: dict         # ready for b4c_request_driver_licence DDL
    address_row: dict         # ready for b4c_request_driver_address DDL


class InvariantViolation(Exception):
    """Raised when an appearance cannot satisfy the matchability invariant after retries."""
    pass


MAX_RETRIES = 10


def verify_invariant(base_person: BasePerson, appearance: QuoteAppearance) -> bool:
    """
    True iff at least one of PK or SK recovers base_person from the observed fields.
    """
    pk_obs = compute_pk(appearance.dl_observed)
    if pk_obs is not None and pk_obs == base_person.pk_truth:
        return True

    if appearance.dob_observed is not None:
        sk_obs = compute_sk(
            appearance.firstname_observed,
            appearance.surname_observed,
            appearance.dob_observed,
        )
        if sk_obs == base_person.sk_truth:
            return True

    return False


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
    Respects max_errors_per_appearance cap: track mutation count, skip further mutations once cap reached.
    Populates all four *_row dicts including all context fields.
    """
    for attempt in range(MAX_RETRIES):
        # Fresh RNG state per attempt is implicit — we use the same rng but draw new random choices

        # Allocate IDs for this appearance
        quote_id = id_counters.next_quote()
        driver_id = id_counters.next_driver()
        licence_id = id_counters.next_licence()
        address_id = id_counters.next_address()

        correlationid = _deterministic_uuid4(rng)
        quote_header_id = _deterministic_uuid4(rng)

        # Generate a single quote_datetime to anchor all timestamps and DAL fields
        quote_datetime = faker.date_time_between(start_date="-30d", end_date="now")

        # Start from base person's canonical values
        firstname_obs = base_person.firstname
        surname_obs = base_person.surname
        dob_obs: Optional[date] = base_person.dob
        dl_obs: Optional[str] = base_person.dl

        applied_noise: dict[str, ErrorType | str | None] = {
            "firstname": None,
            "surname": None,
            "dateofbirth": None,
            "dl": None,
        }

        errors_applied = 0

        # Mutate firstname
        if errors_applied < config.max_errors_per_appearance:
            firstname_obs, err_type = mutate_field("firstname", firstname_obs, config, rng)
            if err_type is not None:
                applied_noise["firstname"] = err_type
                errors_applied += 1

        # Mutate surname
        if errors_applied < config.max_errors_per_appearance:
            surname_obs, err_type = mutate_field("surname", surname_obs, config, rng)
            if err_type is not None:
                applied_noise["surname"] = err_type
                errors_applied += 1

        # Mutate dateofbirth: convert to string YYYY-MM-DD for mutation, then parse back
        if errors_applied < config.max_errors_per_appearance and dob_obs is not None:
            dob_str = dob_obs.strftime("%Y-%m-%d")
            mutated_dob_str, err_type = mutate_field("dateofbirth", dob_str, config, rng)
            if err_type is not None:
                applied_noise["dateofbirth"] = err_type
                errors_applied += 1
                if mutated_dob_str == "":
                    dob_obs = None
                else:
                    try:
                        dob_obs = datetime.strptime(mutated_dob_str, "%Y-%m-%d").date()
                    except ValueError:
                        dob_obs = None

        # Mutate DL via special dispatcher
        if errors_applied < config.max_errors_per_appearance:
            dl_obs, dl_tag = mutate_dl(dl_obs, config, rng)
            applied_noise["dl"] = dl_tag
            if dl_tag != "none":
                errors_applied += 1

        # Check invariant
        if config.allow_unrecoverable_appearances or verify_invariant(base_person, QuoteAppearance(
            correlationid=correlationid,
            quote_header_id=quote_header_id,
            id=quote_id,
            driver_id=driver_id,
            driver_license_id=licence_id,
            driver_address_id=address_id,
            base_person_id=base_person.base_person_id,
            firstname_observed=firstname_obs,
            surname_observed=surname_obs,
            dob_observed=dob_obs,
            dl_observed=dl_obs,
            applied_noise=applied_noise,
            quote_row={},
            driver_row={},
            licence_row={},
            address_row={},
        )):
            # Invariant satisfied — build full rows and return
            quote_row = _build_quote_row(
                quote_id=quote_id,
                correlationid=correlationid,
                quote_header_id=quote_header_id,
                faker=faker,
                rng=rng,
                base_person=base_person,
                quote_datetime=quote_datetime,
            )
            driver_row = _build_driver_row(
                driver_id=driver_id,
                correlationid=correlationid,
                quote_header_id=quote_header_id,
                firstname=firstname_obs,
                surname=surname_obs,
                dob=dob_obs,
                faker=faker,
                rng=rng,
                quote_datetime=quote_datetime,
            )
            licence_row = _build_licence_row(
                driver_license_id=licence_id,
                correlationid=correlationid,
                quote_header_id=quote_header_id,
                driver_id=driver_id,
                dl=dl_obs,
                dob=dob_obs,
                faker=faker,
                rng=rng,
                quote_datetime=quote_datetime,
            )
            address_row = _build_address_row(
                driver_address_id=address_id,
                correlationid=correlationid,
                quote_header_id=quote_header_id,
                driver_id=driver_id,
                address=base_person.address,
                faker=faker,
                quote_datetime=quote_datetime,
            )

            return QuoteAppearance(
                correlationid=correlationid,
                quote_header_id=quote_header_id,
                id=quote_id,
                driver_id=driver_id,
                driver_license_id=licence_id,
                driver_address_id=address_id,
                base_person_id=base_person.base_person_id,
                firstname_observed=firstname_obs,
                surname_observed=surname_obs,
                dob_observed=dob_obs,
                dl_observed=dl_obs,
                applied_noise=applied_noise,
                quote_row=quote_row,
                driver_row=driver_row,
                licence_row=licence_row,
                address_row=address_row,
            )

    # All retries exhausted
    raise InvariantViolation(
        f"Could not satisfy matchability invariant for base_person_id={base_person.base_person_id} "
        f"after {MAX_RETRIES} attempts"
    )


# --- Row builders for context fields ---

def _build_quote_row(
    quote_id: int,
    correlationid: str,
    quote_header_id: str,
    faker: Faker,
    rng: random.Random,
    base_person: BasePerson,
    quote_datetime: datetime,
) -> dict:
    """Construct the b4c_request_quote row with plausible context."""
    brand = rng.choice(["BRAND_A", "BRAND_B", "BRAND_C"])
    startdate = quote_datetime + timedelta(days=rng.randint(14, 60))

    return {
        "id": quote_id,
        "quote_header_id": quote_header_id,
        "correlationid": correlationid,
        "brand": brand,
        "source_timestamp": quote_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        "shredding_timestamp": (quote_datetime + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "pcwrefid": faker.uuid4(),
        "protectnoclaims": rng.choice(["YES", "NO"]),
        "startdate": startdate.strftime("%Y-%m-%d"),
        "coverlevel": rng.choice(["COMPREHENSIVE", "THIRD_PARTY_FIRE_THEFT", "THIRD_PARTY_ONLY"]),
        "paymentfrequency": rng.choice(["MONTHLY", "QUARTERLY", "ANNUALLY"]),
        "voluntaryexcess": str(rng.choice([0, 100, 150, 250, 500])),
        "source": rng.choice(["DIRECT", "COMPARISON", "AFFILIATE"]),
        "channel": rng.choice(["ONLINE", "PHONE"]),
        "line": rng.choice(["PERSONAL", "COMMERCIAL"]),
        "offering": rng.choice(["STANDARD", "PLUS"]),
        "refids": faker.uuid4(),
        "dal_year": quote_datetime.strftime("%Y"),
        "dal_month": quote_datetime.strftime("%m"),
        "dal_day": quote_datetime.strftime("%d"),
    }


def _build_driver_row(
    driver_id: int,
    correlationid: str,
    quote_header_id: str,
    firstname: str,
    surname: str,
    dob: Optional[date],
    faker: Faker,
    rng: random.Random,
    quote_datetime: datetime,
) -> dict:
    """Construct the b4c_request_driver row."""
    title = rng.choice(["MR", "MRS", "MS", "DR"])
    gender = rng.choice(["M", "F"])

    # Use base person's dob if not blanked; otherwise use a plausible fallback
    effective_dob = dob or faker.date_of_birth(minimum_age=18, maximum_age=80)
    startdate = quote_datetime - timedelta(days=rng.randint(365, 365 * 10))

    return {
        "quote_header_id": quote_header_id,
        "correlationid": correlationid,
        "driver_id": driver_id,
        "pcr_drvid": f"DRV-{driver_id}",
        "firstname": firstname,
        "middlename": None,
        "surname": surname,
        "dateofbirth": effective_dob.strftime("%Y-%m-%d %H:%M:%S") if effective_dob else None,
        "title": title,
        "gender": gender,
        "maritalstatus": rng.choice(["SINGLE", "MARRIED", "DIVORCED", "WIDOWED"]),
        "residencesince": (quote_datetime - timedelta(days=rng.randint(365, 365 * 20))).strftime("%Y-%m-%d"),
        "employmentstatus": rng.choice(["EMPLOYED", "SELF_EMPLOYED", "RETIRED", "STUDENT"]),
        "childrenunder16": rng.choice(["YES", "NO"]),
        "carsinhousehold": str(rng.randint(1, 3)),
        "ismaindriver": rng.choice(["YES", "NO"]),
        "isproposer": rng.choice(["YES", "NO"]),
        "relationshiptoproposer": rng.choice(["SELF", "SPOUSE", "PARTNER", "CHILD"]),
        "ishomeowner": rng.choice(["YES", "NO"]),
        "isncdowner": rng.choice(["YES", "NO"]),
        "ncddurationyears": str(rng.randint(0, 15)),
        "ncddurationmonths": str(rng.randint(0, 11)),
        "wasrefusedinsurancebefore": rng.choice(["YES", "NO"]),
        "othervehicleuse": rng.choice(["SOCIAL", "COMMUTING", "BUSINESS"]),
        "startdate": startdate.strftime("%Y-%m-%d %H:%M:%S"),
        "quote_entry_time": quote_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        "source_timestamp": quote_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        "shredding_timestamp": (quote_datetime + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "partition_0": "0",
        "dal_year": quote_datetime.strftime("%Y"),
        "dal_month": quote_datetime.strftime("%m"),
        "dal_day": quote_datetime.strftime("%d"),
    }


def _build_licence_row(
    driver_license_id: int,
    correlationid: str,
    quote_header_id: str,
    driver_id: int,
    dl: Optional[str],
    dob: Optional[date],
    faker: Faker,
    rng: random.Random,
    quote_datetime: datetime,
) -> dict:
    """Construct the b4c_request_driver_licence row."""
    # licencestartdate: DOB + 17 years + random offset (0-3 years)
    if dob:
        # Use year arithmetic to avoid overflow; cap offset so result stays within date range
        base_year = dob.year + 17
        offset_years = rng.randint(0, 3)
        target_year = base_year + offset_years
        # Clamp target_year to a safe maximum (date.max.year - 1) to avoid overflow
        max_safe_year = date.max.year - 1
        if target_year > max_safe_year:
            target_year = max_safe_year
        # Handle Feb 29 -> Feb 28 on non-leap target years
        try:
            licencestartdate = date(target_year, dob.month, dob.day)
        except ValueError:
            # Feb 29 on non-leap year -> use Feb 28
            licencestartdate = date(target_year, dob.month, 28)
    else:
        licencestartdate = faker.date_of_birth(minimum_age=20, maximum_age=70)

    held_years = (quote_datetime.date() - licencestartdate).days // 365

    return {
        "quote_header_id": quote_header_id,
        "correlationid": correlationid,
        "driver_license_id": driver_license_id,
        "pcr_drvid": f"DRV-{driver_id}",
        "driver_id": driver_id,
        "licencenumber": dl,
        "licencetype": "FULL_UK",
        "licencestartdate": licencestartdate.strftime("%Y-%m-%d"),
        "licencestatus": "VALID",
        "medicalconditions": "NONE",
        "licenceheldyears": str(held_years),
        "source_timestamp": quote_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        "shredding_timestamp": (quote_datetime + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "dal_year": quote_datetime.strftime("%Y"),
        "dal_month": quote_datetime.strftime("%m"),
        "dal_day": quote_datetime.strftime("%d"),
    }


def _build_address_row(
    driver_address_id: int,
    correlationid: str,
    quote_header_id: str,
    driver_id: int,
    address: Address,
    faker: Faker,
    quote_datetime: datetime,
) -> dict:
    """Construct the b4c_request_driver_address row (address stable per base person)."""
    return {
        "quote_header_id": quote_header_id,
        "correlationid": correlationid,
        "driver_address_id": driver_address_id,
        "pcr_drvid": f"DRV-{driver_id}",
        "driver_id": driver_id,
        "housenumber": address.housenumber,
        "line1": address.line1,
        "line2": address.line2,
        "line3": None,
        "line4": None,
        "town": address.town,
        "county": address.county,
        "country": address.country,
        "postcode": address.postcode,
        "source_timestamp": quote_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        "shredding_timestamp": (quote_datetime + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "dal_year": quote_datetime.strftime("%Y"),
        "dal_month": quote_datetime.strftime("%m"),
        "dal_day": quote_datetime.strftime("%d"),
    }
