"""
M0 — Canonical entity model for DARPAN.

Defines the shared vocabulary every downstream module (M1 extractor, M2 ETL,
M3 DB, M5 stress engine) will use. This is a *paper schema* — no DB yet.
Frozen in M0 so M1/M2 can build adapters against a stable target.

Entities:
  - Bank          : reporting entity (PSU / private / cooperative / foreign / NBFC)
  - ComplaintCategory : taxonomy of complaint grounds used by RBI
  - Region        : RBI office region (15 ombudsman offices)
  - Year          : reporting period (fiscal year)
  - ComplaintRecord : normalized fact row — one (bank, category, region, year) cell

The complaint record is what every format-era parser must ultimately emit.
The RawComplaintRecord wrapper carries source provenance for auditability.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Reference dimensions
# ---------------------------------------------------------------------------

class BankType(str, Enum):
    PSU = "PSU"
    PRIVATE = "PRIVATE"
    FOREIGN = "FOREIGN"
    COOPERATIVE = "COOPERATIVE"
    RRB = "RRB"
    NBFC = "NBFC"
    SMALL_FINANCE = "SMALL_FINANCE"
    PAYMENTS = "PAYMENTS"
    UNKNOWN = "UNKNOWN"


class Bank(BaseModel):
    """A reporting bank. `rbi_short_code` is the join key across report years."""
    bank_id: str = Field(..., description="Stable internal ID, slug of canonical name")
    canonical_name: str = Field(..., description="Display name e.g. 'State Bank of India'")
    bank_type: BankType
    rbi_short_code: Optional[str] = Field(None, description="Short code as it appears in RBI tables")
    aliases: list[str] = Field(default_factory=list, description="Name variants across years")


class ComplaintCategory(BaseModel):
    """RBI complaint category — taxonomy differs across report years; `code` is the
    canonical post-2021 IOS code; `pre_2021_label` captures older wording."""
    category_id: int
    code: str = Field(..., description="Canonical short code, e.g. 'ATM_DENIED', 'CARD_FRAUD'")
    label: str = Field(..., description="Display label")
    pre_2021_label: Optional[str] = None


class Region(BaseModel):
    """RBI ombudsman office region. 15 offices as of 2021 consolidation."""
    region_id: str = Field(..., description="e.g. 'CHENNAI-I', 'MUMBAI-II'")
    city: str
    state: str
    ombudsman_office_code: Optional[str] = None


class ReportingYear(BaseModel):
    """Indian fiscal year (Apr-Mar). The RBI label is the join key."""
    year_id: str = Field(..., description="e.g. '2019-20'")
    fy_start: date
    fy_end: date
    rbi_label: str = Field(..., description="Verbatim title from report cover")

    @field_validator("fy_start", "fy_end")
    @classmethod
    def _valid_fy(cls, v: date) -> date:
        return v


# ---------------------------------------------------------------------------
# Normalized fact row — the contract every parser must produce
# ---------------------------------------------------------------------------

class DisposalMode(str, Enum):
    AWARD = "AWARD"
    REJECTED = "REJECTED"
    SETTLED = "SETTLED"
    WITHDRAWN = "WITHDRAWN"
    PENDING = "PENDING"
    OTHER = "OTHER"


class ComplaintRecord(BaseModel):
    """One (bank, category, region, year) cell. The unit of analysis."""
    bank_id: str
    category_id: int
    region_id: Optional[str] = None  # some tables are bank-level, no region
    year_id: str
    received: int = Field(..., ge=0)
    disposed: int = Field(..., ge=0)
    pending_at_year_end: int = Field(0, ge=0)
    award_count: int = Field(0, ge=0)
    award_amount_inr: float = Field(0.0, ge=0.0)
    avg_resolution_days: Optional[float] = Field(None, ge=0.0)


class SourceDocRef(BaseModel):
    """Provenance: which PDF + page a row was extracted from. Every M2 row
    must carry one of these so we can audit numbers back to the source."""
    source_doc: str = Field(..., description="PDF filename")
    page_number: int = Field(..., ge=1)
    table_index: Optional[int] = Field(None, description="1-based table index on the page, if identifiable")
    extract_strategy: str = Field(..., description="native | ocr_tesseract | ocr_donut | manual")
    extracted_at: Optional[date] = None


class RawComplaintRecord(BaseModel):
    """Staging wrapper: a ComplaintRecord + its SourceDocRef. M2 emits these
    to the append-only staging table before normalization."""
    record: ComplaintRecord
    source: SourceDocRef
    raw_text_excerpt: Optional[str] = None


# ---------------------------------------------------------------------------
# Convenience: the inventory row the audit produces
# ---------------------------------------------------------------------------

class SourceInventoryRow(BaseModel):
    """One row per source PDF — the output of M0 step 1."""
    filename: str
    reporting_year: str
    size_bytes: int
    page_count: int
    has_text_layer: bool
    text_density: float = Field(..., description="Avg characters per page; <500 implies scan-only")
    metrics_visible: list[str] = Field(default_factory=list,
                                        description="Metrics found by string-sampling (received/disposed/award/NPA…)")
    format_era: str = Field(..., description="pre-2018 | 2018-2021 | post-2021 | unknown")
    extraction_strategy: str = Field(..., description="native | ocr | hybrid")
    confidence: str = Field("high", description="high | medium | low — based on M0 audit signals")


__all__ = [
    "BankType", "Bank",
    "ComplaintCategory",
    "Region",
    "ReportingYear",
    "DisposalMode",
    "ComplaintRecord",
    "SourceDocRef",
    "RawComplaintRecord",
    "SourceInventoryRow",
]
