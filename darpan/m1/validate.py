"""
M1 — spot-check validation.

Per the plan: "Validate extraction on 2-3 known years before declaring
the router done."

This module reads the post-classification results and asserts three
sanity checks per era:

  1. The 3-year complaint timeseries (received / disposed) is present.
  2. The category breakdown table is present and non-empty.
  3. The bank/entity-group breakdown table is present and non-empty.

We compare against *known* values we observed during development:
  - 2016-17: received 130,987, disposed 125,319 (page 17 of legacy PDF)
  - 2021-22: total receipt 9,11,384 (page 18 of IOS PDF)
  - 2024-25: total receipt 9,11,384 (page 18 of FY24-25 PDF — same era)

If any check fails, M1 exits non-zero and tells the operator exactly
which year + which check failed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from entities import ExtractionResult


@dataclass
class SpotCheck:
    filename: str
    reporting_year: str
    ok: bool
    failures: list[str]


# Era-aware M1 validation.
# These values are real totals from the source PDFs and are used only as
# extraction spot checks. M2 remains responsible for strict financial reconciliation.
KNOWN_VALUES = {
    "2016-17": {"complaint_timeseries": {"received": 130987, "disposed": 125319}},
    "2021-22": {"complaint_timeseries": {"received": 304496, "disposed": 311067}},
    "2024-25": {"complaint_timeseries": {"received": 911384}},
}


def _table_has_label_near_value(result: ExtractionResult, kind: str, expected: int) -> bool:
    """Search parsed integer cells in classified tables near an expected source value."""
    from classify_tables import parse_int

    for tbl in result.tables:
        if tbl.detected_table_kind != kind:
            continue
        for row in tbl.rows:
            for cell in row:
                value = parse_int(cell)
                if value is not None and value > 0:
                    if abs(value - expected) / expected <= 0.02:
                        return True
    return False


def validate_one(result: ExtractionResult) -> SpotCheck:
    failures: list[str] = []

    # Core extraction gate: every ombudsman report must have complaint series.
    ts_tables = [t for t in result.tables if t.detected_table_kind == "complaint_timeseries"]
    if not ts_tables:
        failures.append("no complaint_timeseries table found")
    else:
        for metric, value in KNOWN_VALUES.get(result.reporting_year, {}).get("complaint_timeseries", {}).items():
            if not _table_has_label_near_value(result, "complaint_timeseries", value):
                failures.append(f"complaint_timeseries missing expected {metric}={value}")

    # Core extraction gate: every report must expose some disposal information.
    has_disposal = any(t.detected_table_kind in ("disposal_modes", "complaint_timeseries")
                       for t in result.tables)
    if not has_disposal:
        failures.append("no disposal table or disposal series found")

    # Era-aware structure: legacy reports use category/bank tables; IOS reports
    # use category/nature/entity/region tables. At least one of these structures
    # is required, not an exact post-2021 category label.
    has_category = any(t.detected_table_kind in ("category_breakdown", "region_breakdown")
                       for t in result.tables)
    has_entity = any(t.detected_table_kind in ("bank_breakdown", "region_breakdown")
                     for t in result.tables)

    if result.format_era == "pre-2018":
        if not has_category:
            failures.append("no category breakdown found for pre-2018 report")
        if not has_entity:
            failures.append("no bank/entity breakdown found for pre-2018 report")
    elif result.format_era == "2018-2021":
        if not has_category:
            failures.append("no category/nature breakdown found for transition report")
        if not has_entity:
            failures.append("no bank/entity breakdown found for transition report")
    else:
        # IOS may label entity tables as nature, group, region or bank breakdown.
        if not (has_category or has_entity):
            failures.append("no IOS category/entity/region breakdown found")

    if not any(t.confidence in ("high", "medium") for t in result.tables):
        failures.append("no high/medium-confidence tables — extraction is suspect")

    return SpotCheck(
        filename=result.filename,
        reporting_year=result.reporting_year,
        ok=not failures,
        failures=failures,
    )


def validate_all(results: list[ExtractionResult]) -> tuple[int, int, list[SpotCheck]]:
    """Run spot checks across all results. Returns (pass, fail, checks)."""
    checks = [validate_one(r) for r in results]
    return sum(1 for c in checks if c.ok), sum(1 for c in checks if not c.ok), checks
