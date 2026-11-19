"""M2 era adapters. They are deliberately conservative: unknown structures stay in staging,
while normalized facts are emitted only when the table kind and source-year column are unambiguous."""
from __future__ import annotations

import re
from pathlib import Path

from dimensions import DimensionRow, match_dimension, BANKS, CATEGORIES, REGIONS


NUMBER = re.compile(r"-?\d[\d,]*")


def parse_int(value) -> int | None:
    if value is None:
        return None
    text = str(value).replace("\n", " ").strip()
    match = NUMBER.search(text)
    if not match:
        return None
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return None


def source_ref(table: dict) -> dict:
    return table["source"]


def selected_year_column(table: dict, reporting_year: str) -> int | None:
    """Find the column in a timeseries table that represents the report's fiscal year."""
    header = table.get("header_row") or []
    year_fragment = reporting_year
    short = year_fragment.split("-")[1]
    for idx, cell in enumerate(header):
        text = str(cell or "").replace("\n", " ")
        if reporting_year in text or short in text:
            return idx
    # Legacy/OBO tables sometimes put the exact year in a later header row.
    for row in table.get("rows", [])[:3]:
        for idx, cell in enumerate(row):
            text = str(cell or "").replace("\n", " ")
            if reporting_year in text or short in text:
                return idx
    return None


def make_fact(*, year: str, bank_id: str | None, category_id: str | None,
              region_id: str | None, received: int, disposed: int,
              pending: int = 0, award_count: int = 0,
              award_amount: float = 0.0, source: dict,
              raw_text: str) -> dict:
    return {
        "bank_id": bank_id,
        "category_id": category_id,
        "region_id": region_id,
        "year_id": year,
        "received": received,
        "disposed": disposed,
        "pending_at_year_end": pending,
        "award_count": award_count,
        "award_amount_inr": award_amount,
        "avg_resolution_days": None,
        "source_doc": source["source_doc"],
        "page_number": source["page_number"],
        "table_index": source.get("table_index"),
        "extract_strategy": source.get("extract_strategy", "native"),
        "raw_text_excerpt": raw_text,
    }


def adapt_legacy(table: dict, reporting_year: str) -> list[dict]:
    """Pre-2018: BOS-only tables, mostly full names and textual categories."""
    kind = table.get("detected_table_kind")
    if kind not in ("bank_breakdown", "category_breakdown", "complaint_timeseries", "disposal_modes"):
        return []

    facts: list[dict] = []
    year_col = selected_year_column(table, reporting_year)
    for row in table.get("rows", []):
        if not row:
            continue
        label = str(row[0] or "").strip()
        bank = match_dimension(label, BANKS)
        category = match_dimension(label, CATEGORIES)

        value = None
        if year_col is not None and year_col < len(row):
            value = parse_int(row[year_col])
        if value is None:
            continue

        if kind in ("bank_breakdown", "complaint_timeseries") and bank:
            facts.append(make_fact(year=reporting_year, bank_id=bank.id,
                                   category_id=None, region_id=None,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
        elif kind == "category_breakdown" and category:
            facts.append(make_fact(year=reporting_year, bank_id=None,
                                   category_id=category.id, region_id=None,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
    return facts


def adapt_transition(table: dict, reporting_year: str) -> list[dict]:
    """2018-2021: mixed BOS/NBFC terminology and textual category labels."""
    kind = table.get("detected_table_kind")
    if kind not in ("bank_breakdown", "category_breakdown", "complaint_timeseries", "disposal_modes", "region_breakdown"):
        return []

    facts: list[dict] = []
    col = selected_year_column(table, reporting_year)
    for row in table.get("rows", []):
        if not row:
            continue
        label = str(row[0] or "").strip()
        bank = match_dimension(label, BANKS)
        category = match_dimension(label, CATEGORIES)
        region = match_dimension(label, REGIONS)

        numbers = [parse_int(cell) for cell in row]
        numbers = [n for n in numbers if n is not None and n >= 0]
        if not numbers:
            continue

        value = numbers[-1]
        if col is not None and col < len(row):
            parsed = parse_int(row[col])
            if parsed is not None:
                value = parsed

        if kind in ("bank_breakdown", "complaint_timeseries") and bank:
            facts.append(make_fact(year=reporting_year, bank_id=bank.id,
                                   category_id=None, region_id=None,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
        elif kind == "category_breakdown" and category:
            facts.append(make_fact(year=reporting_year, bank_id=None,
                                   category_id=category.id, region_id=None,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
        elif kind == "region_breakdown" and region:
            facts.append(make_fact(year=reporting_year, bank_id=None,
                                   category_id=None, region_id=region.id,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
    return facts


def adapt_ios(table: dict, reporting_year: str) -> list[dict]:
    """Post-2021: IOS unified group/entity/category/region tables."""
    kind = table.get("detected_table_kind")
    if kind not in ("bank_breakdown", "category_breakdown", "complaint_timeseries", "disposal_modes", "region_breakdown"):
        return []

    facts: list[dict] = []
    col = selected_year_column(table, reporting_year)
    for row in table.get("rows", []):
        if not row:
            continue
        label = str(row[0] or "").strip()
        bank = match_dimension(label, BANKS)
        category = match_dimension(label, CATEGORIES)
        region = match_dimension(label, REGIONS)
        numbers = [parse_int(cell) for cell in row]
        numbers = [n for n in numbers if n is not None and n >= 0]
        if not numbers:
            continue

        value = numbers[-1]
        if col is not None and col < len(row):
            parsed = parse_int(row[col])
            if parsed is not None:
                value = parsed

        if kind in ("bank_breakdown", "complaint_timeseries") and bank:
            facts.append(make_fact(year=reporting_year, bank_id=bank.id,
                                   category_id=None, region_id=None,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
        elif kind == "category_breakdown" and category:
            facts.append(make_fact(year=reporting_year, bank_id=None,
                                   category_id=category.id, region_id=None,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
        elif kind == "region_breakdown" and region:
            facts.append(make_fact(year=reporting_year, bank_id=None,
                                   category_id=None, region_id=region.id,
                                   received=value, disposed=0,
                                   source=source_ref(table), raw_text=" | ".join(map(str, row))))
    return facts


def adapt_table(table: dict, reporting_year: str, variant: str) -> list[dict]:
    if variant == "bos_legacy_v1":
        return adapt_legacy(table, reporting_year)
    if variant == "bos_nbfc_transition_v2":
        return adapt_transition(table, reporting_year)
    return adapt_ios(table, reporting_year)
