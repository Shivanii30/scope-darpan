"""
M0 — Format-drift detector and extraction strategy router.

Takes the inventory produced by inspect.py and decides:
  1. Which format era each PDF belongs to (pre-2018 / 2018-2021 / post-2021)
  2. Which extraction strategy to use (native | ocr | hybrid)
  3. The schema variant expected for that era (which tables, which columns)

Era rules (documented from the plan):
  - pre-2018  : single Banking Ombudsman Scheme only; older category labels;
                no NBFC ombudsman; no region split
  - 2018-2021 : transition era; NBFC scheme added; region/office labels still
                inconsistent; some tables rendered as images
  - post-2021 : Integrated Ombudsman Scheme (IOS); unified category taxonomy;
                15 ombudsman offices; standardized table layouts

Strategy rules (driven by inspect.py's text-density signal):
  - has_text_layer AND metrics_visible >= 3  -> native (pdfplumber)
  - has_text_layer AND metrics_visible < 3   -> hybrid (native + targeted OCR on tables)
  - NOT has_text_layer                       -> ocr (Tesseract + LayoutLMv3 fallback)

Outputs:
  - outputs/format_drift_log.json
  - outputs/format_drift_log.md   (human-readable — this is the artifact the
    plan calls out as "prevents 80% of ETL pain")
  - outputs/extraction_strategy_map.csv
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

# Note: do NOT `import inspect` here — it would shadow Python's stdlib inspect
# module that pdfplumber depends on.
from entities import SourceInventoryRow


INPUT_JSON = Path(__file__).resolve().parent / "outputs" / "source_inventory.json"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


# ---------------------------------------------------------------------------
# Era classification
# ---------------------------------------------------------------------------

def fy_to_end_year(year_id: str) -> int | None:
    """'2019-20' -> 2020; '2018' -> 2018. Indian FY ends in the later year."""
    if not year_id or year_id == "unknown":
        return None
    if "-" in year_id:
        parts = year_id.split("-")
        end = parts[1]
        return 2000 + int(end) if len(end) == 2 else int(end)
    return int(year_id)


def classify_era(year_id: str) -> tuple[str, str]:
    """Returns (era, schema_variant). The schema_variant tells M2 which
    parser adapter to wire up.

    Era boundaries (documented from the DARPAN plan):
      - pre-2018   : end_year < 2018  → bos_legacy_v1
      - 2018-2021  : end_year in [2018, 2020]  → bos_nbfc_transition_v2
                     (FY 2017-18 is still legacy; IOS launched Nov 2021)
      - post-2021  : end_year >= 2021  → ios_unified_v3
                     (FY 2021-22 is the first full IOS year, hence end_yr=2022)
    """
    end_yr = fy_to_end_year(year_id)
    if end_yr is None:
        return "unknown", "manual_review"
    if end_yr < 2018:
        return "pre-2018", "bos_legacy_v1"
    if end_yr <= 2020:
        return "2018-2021", "bos_nbfc_transition_v2"
    return "post-2021", "ios_unified_v3"


# ---------------------------------------------------------------------------
# Strategy decision
# ---------------------------------------------------------------------------

def decide_strategy(row: SourceInventoryRow) -> str:
    if row.has_text_layer and len(row.metrics_visible) >= 3:
        return "native"
    if row.has_text_layer and len(row.metrics_visible) < 3:
        return "hybrid"
    return "ocr"


# ---------------------------------------------------------------------------
# Per-era parser notes (the drift log)
# ---------------------------------------------------------------------------

ERA_NOTES: dict[str, dict] = {
    "pre-2018": {
        "title": "BOS legacy (single Banking Ombudsman Scheme)",
        "schema_variant": "bos_legacy_v1",
        "expected_categories_label": "ground of complaint (textual, no codes)",
        "expected_regions": "national total + RBI regional offices (variable count)",
        "expected_tables": ["Bank-wise complaints received/disposed", "Grounds of complaint"],
        "known_gaps": [
            "No NBFC scheme — NBFC complaints absent",
            "Award amount reported in lakhs, not rupees — must normalize",
            "Bank names spelled in full, no short codes",
        ],
    },
    "2018-2021": {
        "title": "BOS + NBFC transition era",
        "schema_variant": "bos_nbfc_transition_v2",
        "expected_categories_label": "mixed textual + early code labels (e.g. 'I', 'II', 'III')",
        "expected_regions": "RBI ombudsman offices (count grew from 15 to 21 in this window)",
        "expected_tables": [
            "Bank-wise complaints",
            "Category-wise (ground-wise) complaints",
            "Disposal mode breakdown",
            "Award table (compensation amounts)",
        ],
        "known_gaps": [
            "Some PDFs in this window are scanned images — must inspect text density",
            "Region labels inconsistent across years — need alias table",
            "Category codes partially introduced — cross-walk table required",
        ],
    },
    "post-2021": {
        "title": "Integrated Ombudsman Scheme (IOS) — unified",
        "schema_variant": "ios_unified_v3",
        "expected_categories_label": "canonical IOS codes (21 grounds, 5 groups)",
        "expected_regions": "15 ombudsman offices, stable labels",
        "expected_tables": [
            "Bank group-wise complaints received/disposed",
            "Grounds-wise complaints",
            "Region-wise complaints",
            "Disposal modes",
            "Award + compensation summary",
        ],
        "known_gaps": [
            "2021-22 is the first IOS year — category labels shifted, M2 needs adapter",
            "Bank grouping by type (PSU/private/foreign/coop) introduced here",
        ],
    },
    "unknown": {
        "title": "Unclassified — manual review",
        "schema_variant": "manual_review",
        "expected_categories_label": "—",
        "expected_regions": "—",
        "expected_tables": [],
        "known_gaps": ["Could not extract reporting year from filename; inspect manually"],
    },
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    if not INPUT_JSON.exists():
        print(f"ERROR: run inspect.py first — missing {INPUT_JSON}", file=sys.stderr)
        return 1

    payload = json.loads(INPUT_JSON.read_text())
    rows = [SourceInventoryRow(**r) for r in payload["rows"]]

    enriched: list[SourceInventoryRow] = []
    for r in rows:
        era, variant = classify_era(r.reporting_year)
        r.format_era = era
        r.extraction_strategy = decide_strategy(r)
        enriched.append(r)

    # ---- JSON: machine-readable drift log ----
    drift_log = {
        "generated_at": date.today().isoformat(),
        "total_pdfs": len(enriched),
        "by_era": {},
        "by_strategy": {},
        "per_pdf": [],
    }
    for r in enriched:
        drift_log["by_era"].setdefault(r.format_era, 0)
        drift_log["by_era"][r.format_era] += 1
        drift_log["by_strategy"].setdefault(r.extraction_strategy, 0)
        drift_log["by_strategy"][r.extraction_strategy] += 1
        drift_log["per_pdf"].append({
            **r.model_dump(),
            "schema_variant": classify_era(r.reporting_year)[1],
        })

    (OUTPUT_DIR / "format_drift_log.json").write_text(json.dumps(drift_log, indent=2))

    # ---- CSV: extraction strategy map (the artifact M1 reads) ----
    with (OUTPUT_DIR / "extraction_strategy_map.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "reporting_year", "format_era", "schema_variant",
                    "extraction_strategy", "has_text_layer", "page_count",
                    "text_density", "confidence"])
        for r in enriched:
            _, variant = classify_era(r.reporting_year)
            w.writerow([r.filename, r.reporting_year, r.format_era, variant,
                        r.extraction_strategy, r.has_text_layer, r.page_count,
                        r.text_density, r.confidence])

    # ---- Markdown: human-readable drift log ----
    md = ["# M0 — Format Drift Log", "",
          f"Generated: {date.today().isoformat()}",
          f"Source dir: `{payload['source_dir']}`",
          "",
          f"**{len(enriched)} PDFs scanned** — {drift_log['by_strategy'].get('native', 0)} native, "
          f"{drift_log['by_strategy'].get('hybrid', 0)} hybrid, "
          f"{drift_log['by_strategy'].get('ocr', 0)} OCR-only.",
          "",
          "## Era distribution", ""]
    for era, n in sorted(drift_log["by_era"].items()):
        notes = ERA_NOTES.get(era, ERA_NOTES["unknown"])
        md.append(f"### {era}  ({n} PDF{'s' if n != 1 else ''})")
        md.append("")
        md.append(f"- **Title:** {notes['title']}")
        md.append(f"- **Schema variant:** `{notes['schema_variant']}`")
        md.append(f"- **Categories:** {notes['expected_categories_label']}")
        md.append(f"- **Regions:** {notes['expected_regions']}")
        if notes["expected_tables"]:
            md.append("- **Expected tables:**")
            for t in notes["expected_tables"]:
                md.append(f"  - {t}")
        if notes["known_gaps"]:
            md.append("- **Known gaps:**")
            for g in notes["known_gaps"]:
                md.append(f"  - {g}")
        md.append("")

    md.append("## Per-PDF decision table")
    md.append("")
    md.append("| File | Year | Era | Strategy | Pages | Text density | Confidence |")
    md.append("|---|---|---|---|---:|---:|---|")
    for r in enriched:
        short = r.filename if len(r.filename) < 60 else r.filename[:57] + "..."
        md.append(f"| `{short}` | {r.reporting_year} | {r.format_era} | "
                  f"`{r.extraction_strategy}` | {r.page_count} | "
                  f"{r.text_density:.0f} | {r.confidence} |")
    md.append("")
    md.append("## How M1 should use this")
    md.append("")
    md.append("1. For each row with `extraction_strategy = native`, M1 calls "
              "pdfplumber on the listed pages and pulls tables via `page.extract_tables()`.")
    md.append("2. For `hybrid`, M1 tries native first; on `page.extract_tables() == []` "
              "or yield with <2 rows, it falls back to OCR on just that page.")
    md.append("3. For `ocr`, M1 routes the whole PDF through Tesseract + LayoutLMv3.")
    md.append("4. The `schema_variant` column tells M2 which parser adapter to wire up.")
    md.append("")
    md.append("> ⚠ **Re-run this audit whenever a new PDF year appears.** "
              "A new format is the #1 silent-corruption risk for downstream scores.")
    md.append("")

    (OUTPUT_DIR / "format_drift_log.md").write_text("\n".join(md), encoding="utf-8")

    print(f"Classified {len(enriched)} PDFs:")
    for era, n in sorted(drift_log["by_era"].items()):
        print(f"  {era:12s}  {n}")
    print()
    print("Wrote outputs/format_drift_log.json")
    print("Wrote outputs/format_drift_log.md")
    print("Wrote outputs/extraction_strategy_map.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
