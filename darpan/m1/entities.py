"""
M1 — entities re-used from M0 plus M1-specific extraction artifacts.

M1's job: take raw PDF pages and emit one `ExtractedTable` per detected
table on each page, then a list of candidate `RawComplaintRecord`s
emitted by the row-classifier. M2's job is to validate and load these
into the staging table.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# Re-export M0 entities so M1's public surface is self-contained.
# Handle both `python -m darpan.m1` and `python run.py from inside m1/`.
try:
    from m0.entities import (
        Bank,
        ComplaintCategory,
        ComplaintRecord,
        DisposalMode,
        RawComplaintRecord,
        Region,
        ReportingYear,
        SourceDocRef,
    )
except ModuleNotFoundError:
    import sys
    from pathlib import Path
    _here = Path(__file__).resolve().parent
    sys.path.insert(0, str(_here.parent))  # darpan/
    from m0.entities import (
        Bank,
        ComplaintCategory,
        ComplaintRecord,
        DisposalMode,
        RawComplaintRecord,
        Region,
        ReportingYear,
        SourceDocRef,
    )


# ---------------------------------------------------------------------------
# Extraction-layer types
# ---------------------------------------------------------------------------

class ExtractedTable(BaseModel):
    """One table found on one page of one PDF. The atomic output of M1's
    native extractor. M2's job is to parse these into ComplaintRecord rows."""
    source: SourceDocRef
    page_number: int
    table_index_on_page: int
    n_rows: int
    n_cols: int
    rows: list[list[Optional[str]]]
    header_row: list[Optional[str]] = Field(default_factory=list)
    detected_table_kind: str = Field(
        "unknown",
        description=(
            "heuristic label: complaint_timeseries | category_breakdown | "
            "bank_breakdown | disposal_modes | award_summary | region_breakdown | "
            "toc | unknown"
        ),
    )
    confidence: str = Field("low", description="high | medium | low — parser confidence in row parseability")


class ExtractionResult(BaseModel):
    """The full M1 output for one PDF: every page scanned, every table found."""
    filename: str
    reporting_year: str
    format_era: str
    schema_variant: str
    extraction_strategy: str
    pages_scanned: int
    pages_with_tables: int
    tables_extracted: int
    tables: list[ExtractedTable]
    started_at: Optional[date] = None
    finished_at: Optional[date] = None
    warnings: list[str] = Field(default_factory=list)


class CandidateRecord(BaseModel):
    """M1's candidate-row envelope. M1 doesn't know canonical bank_id /
    category_id / region_id — those come from M2's dimension lookups.
    We hand M2 the raw label + parsed numeric metrics + source ref."""
    entity_label: str = Field(..., description="First-column label, e.g. 'Public Sector Banks' or 'ATM/ Debit Cards'")
    table_kind: str = Field(..., description="One of: complaint_timeseries | category_breakdown | bank_breakdown | disposal_modes | award_summary | region_breakdown | appeals | unknown")
    metrics: list[int] = Field(default_factory=list, description="All positive integer cells in the row, in column order")
    source: SourceDocRef
    row_index_in_table: int
    raw_row: list[Optional[str]] = Field(default_factory=list)


__all__ = [
    # M0 re-exports
    "Bank", "ComplaintCategory", "ComplaintRecord", "DisposalMode",
    "RawComplaintRecord", "Region", "ReportingYear", "SourceDocRef",
    # M1-native
    "ExtractedTable", "ExtractionResult", "CandidateRecord",
]
