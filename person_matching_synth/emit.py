"""CSV emission for the four tables and ground truth sidecar."""

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from .appearance import QuoteAppearance
from .config import GeneratorConfig, ErrorType


# Column order per DDL field inventory (§2.2)
QUOTE_COLUMNS = [
    "id",
    "quote_header_id",
    "correlationid",
    "brand",
    "source_timestamp",
    "shredding_timestamp",
    "pcwrefid",
    "protectnoclaims",
    "startdate",
    "coverlevel",
    "paymentfrequency",
    "voluntaryexcess",
    "source",
    "channel",
    "line",
    "offering",
    "refids",
    "dal_year",
    "dal_month",
    "dal_day",
]

DRIVER_COLUMNS = [
    "quote_header_id",
    "correlationid",
    "driver_id",
    "pcr_drvid",
    "firstname",
    "middlename",
    "surname",
    "dateofbirth",
    "title",
    "gender",
    "maritalstatus",
    "residencesince",
    "employmentstatus",
    "childrenunder16",
    "carsinhousehold",
    "ismaindriver",
    "isproposer",
    "relationshiptoproposer",
    "ishomeowner",
    "isncdowner",
    "ncddurationyears",
    "ncddurationmonths",
    "wasrefusedinsurancebefore",
    "othervehicleuse",
    "startdate",
    "quote_entry_time",
    "source_timestamp",
    "shredding_timestamp",
    "partition_0",
    "dal_year",
    "dal_month",
    "dal_day",
]

LICENCE_COLUMNS = [
    "quote_header_id",
    "correlationid",
    "driver_license_id",
    "pcr_drvid",
    "driver_id",
    "licencenumber",
    "licencetype",
    "licencestartdate",
    "licencestatus",
    "medicalconditions",
    "licenceheldyears",
    "source_timestamp",
    "shredding_timestamp",
    "dal_year",
    "dal_month",
    "dal_day",
]

ADDRESS_COLUMNS = [
    "quote_header_id",
    "correlationid",
    "driver_address_id",
    "pcr_drvid",
    "driver_id",
    "housenumber",
    "line1",
    "line2",
    "line3",
    "line4",
    "town",
    "county",
    "country",
    "postcode",
    "source_timestamp",
    "shredding_timestamp",
    "dal_year",
    "dal_month",
    "dal_day",
]

GROUND_TRUTH_COLUMNS = [
    "correlationid",
    "driver_id",
    "base_person_id",
    "applied_noise_firstname",
    "applied_noise_surname",
    "applied_noise_dob",
    "applied_noise_dl",
    "dl_mutation_class",
]


def _format_date_or_none(d: Optional[date]) -> Optional[str]:
    if d is None:
        return None
    return d.strftime("%Y-%m-%d")


def _format_datetime_or_none(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "b4c_request_quote.csv": output_dir / "b4c_request_quote.csv",
        "b4c_request_driver.csv": output_dir / "b4c_request_driver.csv",
        "b4c_request_driver_licence.csv": output_dir / "b4c_request_driver_licence.csv",
        "b4c_request_driver_address.csv": output_dir / "b4c_request_driver_address.csv",
    }

    # Open all files once and stream rows
    with (
        open(paths["b4c_request_quote.csv"], "w", newline="", encoding="utf-8") as f_quote,
        open(paths["b4c_request_driver.csv"], "w", newline="", encoding="utf-8") as f_driver,
        open(paths["b4c_request_driver_licence.csv"], "w", newline="", encoding="utf-8") as f_licence,
        open(paths["b4c_request_driver_address.csv"], "w", newline="", encoding="utf-8") as f_address,
    ):
        writers = {
            "quote": csv.DictWriter(f_quote, fieldnames=QUOTE_COLUMNS, extrasaction="ignore"),
            "driver": csv.DictWriter(f_driver, fieldnames=DRIVER_COLUMNS, extrasaction="ignore"),
            "licence": csv.DictWriter(f_licence, fieldnames=LICENCE_COLUMNS, extrasaction="ignore"),
            "address": csv.DictWriter(f_address, fieldnames=ADDRESS_COLUMNS, extrasaction="ignore"),
        }
        for writer in writers.values():
            writer.writeheader()

        # Ground truth file
        gt_path = None
        gt_file = None
        gt_writer = None
        if config.emit_ground_truth:
            gt_path = output_dir / "ground_truth.csv"
            gt_file = open(gt_path, "w", newline="", encoding="utf-8")
            gt_writer = csv.DictWriter(gt_file, fieldnames=GROUND_TRUTH_COLUMNS, extrasaction="ignore")
            gt_writer.writeheader()

        try:
            for app in appearances:
                # Write each table row (DictWriter ignores extra keys)
                writers["quote"].writerow(app.quote_row)
                writers["driver"].writerow(app.driver_row)
                writers["licence"].writerow(app.licence_row)
                writers["address"].writerow(app.address_row)

                if gt_writer:
                    def _serialise_noise(v):
                        if v is None:
                            return ""
                        if isinstance(v, ErrorType):
                            return v.value
                        return str(v)
                    gt_writer.writerow({
                        "correlationid": app.correlationid,
                        "driver_id": app.driver_id,
                        "base_person_id": app.base_person_id,
                        "applied_noise_firstname": _serialise_noise(app.applied_noise.get("firstname")),
                        "applied_noise_surname": _serialise_noise(app.applied_noise.get("surname")),
                        "applied_noise_dob": _serialise_noise(app.applied_noise.get("dateofbirth")),
                        "applied_noise_dl": _serialise_noise(app.applied_noise.get("dl")),
                        "dl_mutation_class": app.applied_noise.get("dl") or "",
                    })
        finally:
            if gt_file:
                gt_file.close()

    if config.emit_ground_truth:
        paths["ground_truth.csv"] = gt_path  # type: ignore

    return paths
