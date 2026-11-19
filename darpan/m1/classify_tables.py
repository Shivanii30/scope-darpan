"""
M1 — table classifier.

Takes the raw ExtractedTable list from native_extractor and labels each
table with a `detected_table_kind` so M2's parser adapters know what
they're looking at. Also walks each table and emits candidate
CandidateRecord rows when it can confidently parse the cells.

The classifier is intentionally conservative. It emits rows only when:
  - the table kind is recognized (complaint_timeseries, category_breakdown,
    bank_breakdown, disposal_modes, award_summary, region_breakdown,
    appeals), AND
  - the row's first column is a non-empty label, AND
  - at least one cell is a positive integer.

The M0 plan's note applies: "Don't assume one extractor works for all
years. Validate extraction on 2-3 known years before declaring the
router done." The validator (validate.py) uses these same labels.
"""
from __future__ import annotations

import re
from typing import Optional

from entities import CandidateRecord, ExtractedTable, ExtractionResult, SourceDocRef


# ---------------------------------------------------------------------------
# Heuristics: what does each table kind *look like* in RBI PDFs?
# ---------------------------------------------------------------------------

# Order matters — earlier patterns are more specific.
KIND_SIGNALS: list[tuple[str, list[str]]] = [
    ("toc",                ["page no.", "s.no.", "s.n.o.", "table no."]),
    ("bank_breakdown",      ["bank-wise", "bank wise", "bank group",
                              "public sector banks", "private sector banks",
                              "entity type-wise", "entity type wise",
                              "entity group"]),
    ("complaint_timeseries", ["complaints brought forward", "complaints received",
                              "complaints disposed", "disposed of during the year",
                              "total no of complaints handled",
                              "total receipt of complaints",
                              # multi-year column header fragments
                              "f.y.\n", "f.y. 20", "(apr-", "(jul-",
                              "complaints received at crpc"]),
    ("category_breakdown",  ["category-wise", "category wise", "category of complaints",
                              "non-observance of fair practice", "atm/debit",
                              "credit cards", "mobile / electronic banking",
                              "grounds-wise", "grounds wise",
                              "nature of complaints", "nature of complaint",
                              "top five categories", "top 5 categories",
                              "category-wise receipt", "grounds/reasons",
                              # IOS codes
                              "ground-i", "ground-ii", "ground-iii",
                              "non-adherence", "account opening"]),
    ("region_breakdown",    ["office of the ombudsman", "orbio", "zone-wise", "zone wise",
                              "office-wise", "office wise", "state-wise"]),
    ("disposal_modes",      ["mode of disposal", "award passed", "settlement",
                              "rejection", "grounds for rejection"]),
    ("award_summary",       ["award amount", "compensation amount", "total amount",
                              "amount of compensation"]),
    ("appeals",             ["appeals", "appeal against", "appeal received"]),
]

# Heuristic guard: tables that are obviously not data
SKIP_IF_HEADER_CONTAINS = ["s.no.", "s.n.o.", "abbreviations",
                            "contents", "table of contents"]


def _cell_text(c) -> str:
    """pdfplumber sometimes returns a list (cell wraps to multiple lines).
    Coerce to a flat string defensively."""
    if c is None:
        return ""
    if isinstance(c, list):
        c = " ".join(str(x) for x in c)
    return str(c).strip().lower()


def _row_text(row) -> str:
    return " ".join(_cell_text(c) for c in row)


def classify_table(tbl: ExtractedTable) -> str:
    """Heuristically label one extracted table. Defaults to 'unknown'."""
    haystack = _row_text(tbl.header_row) + " " + _row_text(tbl.rows[:3])
    if not haystack.strip():
        return "unknown"
    if any(token in haystack for token in SKIP_IF_HEADER_CONTAINS):
        return "toc"
    for kind, signals in KIND_SIGNALS:
        if any(sig in haystack for sig in signals):
            return kind
    return "unknown"


# ---------------------------------------------------------------------------
# Numeric parsing
# ---------------------------------------------------------------------------

NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_int(cell) -> Optional[int]:
    """Parse '1,54,725' or '130,987' or '8497' (Indian / US digit grouping).
    Returns None if no digits present."""
    if cell is None:
        return None
    s = str(cell)
    m = NUM_RE.search(s.replace("\n", " "))
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Row -> candidate record emission
# ---------------------------------------------------------------------------

def _first_cell(row) -> str:
    return _cell_text(row[0]) if row else ""


def emit_candidates(tbl: ExtractedTable) -> list[CandidateRecord]:
    """Walk the table rows and emit CandidateRecord rows.
    Conservative: only emit when the row's first cell is non-empty and
    at least one data cell is a positive integer."""
    kind = tbl.detected_table_kind
    if kind in ("unknown", "toc"):
        return []

    out: list[CandidateRecord] = []
    rows = tbl.rows[1:] if len(tbl.rows) > 1 else []  # skip header row

    for row in rows:
        if not row or not any((c or "").strip() for c in row):
            continue
        entity_label = _first_cell(row)
        if not entity_label or len(entity_label) < 2:
            continue
        if entity_label.startswith("total"):  # skip totals; M2 re-derives
            continue

        # All cells to the right of the label, parsed as ints
        numeric_cells = [parse_int(c) for c in row[1:]]
        positive_metrics = [n for n in numeric_cells if n is not None and n >= 0]
        if not positive_metrics:
            continue

        try:
            row_idx = tbl.rows.index(row)
        except ValueError:
            row_idx = -1

        out.append(CandidateRecord(
            entity_label=entity_label,
            table_kind=kind,
            metrics=positive_metrics,
            source=tbl.source,
            row_index_in_table=row_idx,
            raw_row=row,
        ))
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def classify_and_extract(result: ExtractionResult) -> int:
    """Walk result.tables, label each, emit candidate records.
    Returns count of records emitted. Mutates result.tables in place.

    Two-pass approach:
      Pass 1: label each table from its own header + first rows.
      Pass 2: a table with no recognizable kind that *follows* a labeled
              table on the same page inherits the same kind (RBI PDFs often
              have multi-section pages where pdfplumber splits the header
              and data into separate 'tables').
    """
    # Pass 1: independent classification
    for tbl in result.tables:
        tbl.detected_table_kind = classify_table(tbl)

    # Pass 2: context-aware inheritance (same page, within 2 tables)
    last_kind_per_page: dict[tuple[str, int], str] = {}
    for tbl in result.tables:
        key = (tbl.source.source_doc, tbl.page_number)
        if tbl.detected_table_kind == "unknown":
            # Inherit from a recent table on the same page if it had a kind
            inherited = last_kind_per_page.get(key)
            if inherited and inherited not in ("unknown", "toc"):
                tbl.detected_table_kind = inherited
        else:
            last_kind_per_page[key] = tbl.detected_table_kind

    # Final: confidence + emit candidates
    emitted = 0
    for tbl in result.tables:
        if tbl.detected_table_kind != "unknown":
            tbl.confidence = "high" if tbl.n_rows >= 3 else "medium"
        else:
            tbl.confidence = "low"
        emitted += len(emit_candidates(tbl))
    return emitted
