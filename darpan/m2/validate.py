"""M2 reconciliation gates."""
from __future__ import annotations

import csv
from pathlib import Path


EXPECTED_YEARS = {"2016-17", "2017-18", "2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"}


def validate(normalized_csv: Path, staging_csv: Path) -> dict:
    errors: list[str] = []

    with normalized_csv.open("r", encoding="utf-8") as f:
        facts = list(csv.DictReader(f))

    years = {row["year_id"] for row in facts}
    missing = sorted(EXPECTED_YEARS - years)
    if missing:
        errors.append("missing normalized year coverage: " + ", ".join(missing))

    for row in facts:
        for field in ("received", "disposed", "pending_at_year_end", "award_count"):
            if int(row[field] or 0) < 0:
                errors.append(f"negative {field} in source {row['source_doc']} page {row['page_number']}")
        if not row["source_doc"] or int(row["page_number"] or 0) < 1:
            errors.append("fact missing source provenance")

    duplicate_keys: set[tuple] = set()
    duplicate_count = 0
    for row in facts:
        key = (row["bank_id"], row["category_id"], row["region_id"], row["year_id"],
               row["received"], row["disposed"], row["source_doc"], row["page_number"])
        if key in duplicate_keys:
            duplicate_count += 1
        duplicate_keys.add(key)

    if duplicate_count:
        errors.append(f"{duplicate_count} duplicate normalized facts remained")

    with staging_csv.open("r", encoding="utf-8") as f:
        staging_count = sum(1 for _ in csv.DictReader(f))

    return {
        "ok": not errors,
        "errors": errors,
        "normalized_facts": len(facts),
        "staging_tables": staging_count,
        "years_covered": sorted(years),
        "duplicate_facts": duplicate_count,
    }
