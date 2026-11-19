"""
M0 — PDF inspector.

Walks the Ombudsman/ directory, opens each PDF with pdfplumber, and reports:
  - page count
  - whether the PDF has a real text layer (chars/page) or is image-only
  - which canonical metric labels it can see by string sampling
  - inferred reporting year (from the filename)

Outputs:
  - outputs/source_inventory.json   (machine-readable)
  - outputs/source_inventory.csv    (human-readable, one row per PDF)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pdfplumber

from entities import SourceInventoryRow


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "Ombudsman"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

# Canonical metrics we expect to see in any usable RBI ombudsman report.
# If a PDF is missing most of these, M1's native extractor won't be able to
# build a ComplaintRecord from it without OCR.
METRIC_KEYWORDS = [
    "complaints received",
    "complaints disposed",
    "maintainable",
    "non-maintainable",
    "award",
    "compensation",
    "amount",
    "bank",
    "category",
    "region",
    "office of the ombudsman",
    "ground",
    "atm",
    "card",
    "deposit",
    "loan",
    "non-banking",
]

# Heuristic thresholds — tuned against known RBI PDF behavior.
TEXT_DENSITY_NATIVE = 800      # >= 800 chars/page on average => native text layer
TEXT_DENSITY_MIXED = 100       # 100–800 => mixed (some pages scanned)
# below 100 => scan-only, must OCR


# ---------------------------------------------------------------------------
# Year extraction from filename
# ---------------------------------------------------------------------------

YEAR_PATTERNS = [
    r"20\d{2}[-–][20]?\d{2}",    # 2019-20, 2019–20, 2019-2020  (match first — preserves full FY)
    r"year\s*(20\d{2})",          # "year 2018"
    r"(20\d{2})",                 # fallback: first 4-digit year
]


def extract_year_from_name(name: str) -> str:
    """Pull the reporting year out of the PDF filename. Returns 'unknown' if
    no plausible year is found — this is itself an audit signal."""
    stem = Path(name).stem
    # 1. Full fiscal-year pattern (e.g. "2019-20", "2018-19")
    m = re.search(r"(20\d{2})[-–]([20]?\d{2})", stem)
    if m:
        a, b = m.group(1), m.group(2)
        # Normalize: "2019-2020" -> "2019-20"; "2019-20" stays as-is
        if len(b) == 4:
            b = b[2:]
        return f"{a}-{b}"
    # 2. "year 2018" or bare 4-digit
    m = re.search(r"year\s*(20\d{2})", stem, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"(20\d{2})", stem)
    if m:
        return m.group(1)
    return "unknown"


# ---------------------------------------------------------------------------
# Per-PDF inspection
# ---------------------------------------------------------------------------

def inspect_pdf(path: Path) -> SourceInventoryRow:
    """Open one PDF, sample its text layer, and return an inventory row."""
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        char_total = 0
        # Sample first 5 pages plus every 10th — keeps the audit fast on big PDFs
        sample_indices = list(range(min(5, page_count)))
        sample_indices += [i for i in range(0, page_count, 10)]
        sample_indices = sorted(set(i for i in sample_indices if 0 <= i < page_count))

        text_chunks: list[str] = []
        for i in sample_indices:
            text = pdf.pages[i].extract_text() or ""
            text_chunks.append(text)
            char_total += len(text)

        sampled_pages = len(sample_indices) or 1
        avg_chars_per_page = char_total / sampled_pages
        full_text = "\n".join(text_chunks).lower()

    has_text_layer = avg_chars_per_page >= TEXT_DENSITY_MIXED
    metrics_visible = [m for m in METRIC_KEYWORDS if m in full_text]

    return SourceInventoryRow(
        filename=path.name,
        reporting_year=extract_year_from_name(path.name),
        size_bytes=path.stat().st_size,
        page_count=page_count,
        has_text_layer=has_text_layer,
        text_density=round(avg_chars_per_page, 1),
        metrics_visible=metrics_visible,
        format_era="unknown",       # filled by era classifier
        extraction_strategy="unknown",  # filled by strategy router
        confidence="high" if has_text_layer and len(metrics_visible) >= 3 else (
            "medium" if has_text_layer else "low"),
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    if not SOURCE_DIR.exists():
        print(f"ERROR: source dir not found: {SOURCE_DIR}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(SOURCE_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"ERROR: no PDFs found in {SOURCE_DIR}", file=sys.stderr)
        return 1

    print(f"M0 inspector — scanning {len(pdfs)} PDFs in {SOURCE_DIR}")
    rows: list[SourceInventoryRow] = []
    for p in pdfs:
        try:
            row = inspect_pdf(p)
            rows.append(row)
            flag = "OK " if row.has_text_layer else "OCR"
            print(f"  [{flag}] {row.filename[:55]:55s}  "
                  f"{row.page_count:4d} pp  "
                  f"{row.text_density:7.1f} chars/p  "
                  f"yr={row.reporting_year}")
        except Exception as e:
            print(f"  [ERR] {p.name}: {e}", file=sys.stderr)
            rows.append(SourceInventoryRow(
                filename=p.name,
                reporting_year=extract_year_from_name(p.name),
                size_bytes=p.stat().st_size,
                page_count=0,
                has_text_layer=False,
                text_density=0.0,
                metrics_visible=[],
                format_era="unknown",
                extraction_strategy="manual",
                confidence="low",
            ))

    # Persist outputs
    json_path = OUTPUT_DIR / "source_inventory.json"
    csv_path = OUTPUT_DIR / "source_inventory.csv"

    payload = {
        "generated_at": __import__("datetime").date.today().isoformat(),
        "source_dir": str(SOURCE_DIR),
        "total_pdfs": len(rows),
        "native_text_pdfs": sum(1 for r in rows if r.has_text_layer),
        "ocr_required_pdfs": sum(1 for r in rows if not r.has_text_layer),
        "rows": [r.model_dump() for r in rows],
    }
    json_path.write_text(json.dumps(payload, indent=2))

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "reporting_year", "size_bytes", "page_count",
                    "has_text_layer", "text_density", "format_era",
                    "extraction_strategy", "confidence", "metrics_visible"])
        for r in rows:
            w.writerow([r.filename, r.reporting_year, r.size_bytes, r.page_count,
                        r.has_text_layer, r.text_density, r.format_era,
                        r.extraction_strategy, r.confidence,
                        "|".join(r.metrics_visible)])

    print(f"\nWrote {json_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {csv_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
