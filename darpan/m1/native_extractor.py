"""
M1 — native pdfplumber extractor.

Walks every page of a PDF, calls `page.extract_tables()`, and emits
`ExtractedTable` records with full source provenance. Tables are also
flushed to disk under outputs/extracted/<year>/<file>.tables.jsonl so
M2 (ETL) can re-parse without re-running pdfplumber.

The classifier downstream (classify_tables.py) reads these and decides
which tables are real complaint data vs. TOC noise.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

# Important: do NOT `import inspect` here — that shadows Python's stdlib
# inspect module which pdfplumber uses during initialization.
import pdfplumber

from entities import ExtractedTable, ExtractionResult, SourceDocRef
from router import RouterDecision


# ---------------------------------------------------------------------------
# Per-PDF extraction
# ---------------------------------------------------------------------------

def extract_native(decision: RouterDecision, out_dir: Path) -> ExtractionResult:
    """Extract every table on every page of one PDF using pdfplumber's
    native table finder. Persist to disk; return in-memory result."""
    result = ExtractionResult(
        filename=decision.filename,
        reporting_year=decision.reporting_year,
        format_era=decision.format_era,
        schema_variant=decision.schema_variant,
        extraction_strategy=decision.strategy,
        pages_scanned=0,
        pages_with_tables=0,
        tables_extracted=0,
        tables=[],
        started_at=date.today(),
    )

    # Pre-create the per-PDF output dir; we flush each table on the fly
    # so even a mid-run crash leaves evidence on disk.
    pdf_out_dir = out_dir / decision.reporting_year / _safe_stem(decision.filename)
    pdf_out_dir.mkdir(parents=True, exist_ok=True)
    tables_jsonl = pdf_out_dir / "tables.jsonl"
    tables_jsonl.write_text("")  # truncate

    with pdfplumber.open(decision.pdf_path) as pdf:
        n_pages = len(pdf.pages)
        for page_idx in range(n_pages):
            page = pdf.pages[page_idx]
            result.pages_scanned = page_idx + 1
            try:
                tables = page.extract_tables() or []
            except Exception as e:
                msg = f"page {page_idx+1}: extract_tables failed: {e}"
                result.warnings.append(msg)
                print(f"  WARN {decision.filename} {msg}", file=sys.stderr)
                continue

            if not tables:
                try:
                    import camelot
                    for flavor in ("lattice", "stream"):
                        fallback = camelot.read_pdf(
                            str(decision.pdf_path),
                            pages=str(page_idx + 1),
                            flavor=flavor,
                        )
                        for extracted in fallback:
                            rows = [[cell if cell is not None else ""
                                     for cell in row]
                                    for row in extracted.df.values.tolist()
                                    if len(row) > 0]
                            if len(rows) >= 2:
                                tables.append(rows)
                        if tables:
                            break
                except Exception as e:
                    msg = f"page {page_idx+1}: camelot fallback failed: {e}"
                    result.warnings.append(msg)
                    print(f"  WARN {decision.filename} {msg}", file=sys.stderr)

            if not tables:
                continue
            result.pages_with_tables += 1

            for t_idx, raw_rows in enumerate(tables):
                if not raw_rows:
                    continue
                # Normalize: pdfplumber returns None for empty cells.
                rows = [[(c if c is not None else "") for c in row] for row in raw_rows]
                header = rows[0] if rows else []
                tbl = ExtractedTable(
                    source=SourceDocRef(
                        source_doc=decision.filename,
                        page_number=page_idx + 1,
                        table_index=t_idx + 1,
                        extract_strategy="native",
                    ),
                    page_number=page_idx + 1,
                    table_index_on_page=t_idx + 1,
                    n_rows=len(rows),
                    n_cols=max((len(r) for r in rows), default=0),
                    rows=rows,
                    header_row=header,
                )
                result.tables.append(tbl)
                result.tables_extracted += 1
                # Persist immediately
                with tables_jsonl.open("a", encoding="utf-8") as f:
                    f.write(tbl.model_dump_json() + "\n")

    result.finished_at = date.today()
    return result


def _safe_stem(name: str) -> str:
    """Filesystem-safe filename stem for use as a directory name."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in Path(name).stem)[:80]
