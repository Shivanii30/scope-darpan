"""
M1 — end-to-end runner.

Steps:
  1. router.py       — read M0's strategy map, decide per-PDF strategy
  2. native_extractor — extract tables via pdfplumber, persist per-PDF JSONL
  3. classify_tables  — label tables + emit candidate records
  4. validate.py     — spot-check on 3 known years
  5. summary report   — JSON index across all PDFs

Run:
    python run.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

# allow `python run.py` from inside the m1 dir
sys.path.insert(0, str(Path(__file__).resolve().parent))

import classify_tables  # noqa: E402
import native_extractor  # noqa: E402
import router  # noqa: E402
import validate  # noqa: E402
from entities import ExtractionResult  # noqa: E402


OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
EXTRACTED_DIR = OUTPUT_DIR / "extracted"


def _safe_stem(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in Path(name).stem)[:80]


def main() -> int:
    print("=" * 64)
    print("M1 — PDF extraction engine")
    print("=" * 64)
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Step 1: route ----
    print("Step 1/4 — router: dispatching per M0's strategy map")
    print("-" * 64)
    decisions = router.load_strategy_map()
    print(f"  {len(decisions)} PDFs to process")
    by_strategy: dict[str, int] = {}
    for d in decisions:
        by_strategy[d.strategy] = by_strategy.get(d.strategy, 0) + 1
    for s, n in sorted(by_strategy.items()):
        print(f"    {s:8s}  {n}")
    print()

    # ---- Step 2: extract ----
    print("Step 2/4 — native_extractor: walking every page of every PDF")
    print("-" * 64)
    results: list[ExtractionResult] = []
    for d in decisions:
        try:
            extractor = router.dispatch(d)
        except NotImplementedError as e:
            print(f"  SKIP  {d.filename}: {e}")
            continue

        print(f"  [{d.strategy:6s}] {d.filename[:60]}")
        result = extractor(d, EXTRACTED_DIR)
        results.append(result)
        print(f"           {result.pages_scanned} pages, "
              f"{result.pages_with_tables} with tables, "
              f"{result.tables_extracted} tables extracted")
    print()

    # ---- Step 3: classify ----
    print("Step 3/4 — classify_tables: labeling each table + emitting candidates")
    print("-" * 64)
    total_candidates = 0
    for r in results:
        n = classify_tables.classify_and_extract(r)
        total_candidates += n

        pdf_out_dir = EXTRACTED_DIR / r.reporting_year / _safe_stem(r.filename)
        pdf_out_dir.mkdir(parents=True, exist_ok=True)

        classified_path = pdf_out_dir / "tables.jsonl"
        with classified_path.open("w", encoding="utf-8") as f:
            for tbl in r.tables:
                f.write(tbl.model_dump_json() + "\n")

        candidates_path = pdf_out_dir / "candidates.jsonl"
        with candidates_path.open("w", encoding="utf-8") as f:
            for tbl in r.tables:
                for candidate in classify_tables.emit_candidates(tbl):
                    f.write(candidate.model_dump_json() + "\n")

        # Per-PDF kind distribution
        kinds: dict[str, int] = {}
        for t in r.tables:
            kinds[t.detected_table_kind] = kinds.get(t.detected_table_kind, 0) + 1
        kind_str = "  ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
        print(f"  {r.filename[:50]:50s}  -> {n} candidates | {kind_str}")
    print(f"\n  Total candidate records emitted: {total_candidates}")
    print()

    # ---- Step 4: validate ----
    print("Step 4/4 — validate: spot-check on known years")
    print("-" * 64)
    passed, failed, checks = validate.validate_all(results)
    for c in checks:
        status = "PASS" if c.ok else "FAIL"
        print(f"  [{status}] {c.filename[:50]:50s}  ({c.reporting_year})")
        for fail in c.failures:
            print(f"         - {fail}")
    print(f"\n  {passed} passed, {failed} failed")
    print()

    # ---- Write summary ----
    summary = {
        "generated_at": date.today().isoformat(),
        "pdfs_processed": len(results),
        "total_tables_extracted": sum(r.tables_extracted for r in results),
        "total_candidates_emitted": total_candidates,
        "spot_checks": {
            "passed": passed, "failed": failed,
            "details": [
                {"filename": c.filename, "reporting_year": c.reporting_year,
                 "ok": c.ok, "failures": c.failures}
                for c in checks
            ],
        },
        "per_pdf": [
            {
                "filename": r.filename,
                "reporting_year": r.reporting_year,
                "format_era": r.format_era,
                "schema_variant": r.schema_variant,
                "pages_scanned": r.pages_scanned,
                "pages_with_tables": r.pages_with_tables,
                "tables_extracted": r.tables_extracted,
                "tables_by_kind": {
                    k: sum(1 for t in r.tables if t.detected_table_kind == k)
                    for k in {t.detected_table_kind for t in r.tables}
                },
                "warnings": r.warnings,
            }
            for r in results
        ],
    }
    summary_path = OUTPUT_DIR / "extraction_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("=" * 64)
    if failed == 0:
        print(f"M1 complete. {passed}/{len(results)} PDFs validated.")
        print("  Outputs:    darpan/m1/outputs/extracted/<year>/<file>.tables.jsonl")
        print("  Summary:    darpan/m1/outputs/extraction_summary.json")
        print("  Next:       M2 (ETL & schema reconciliation)")
        print("=" * 64)
        return 0
    else:
        print(f"M1 complete with {failed} validation failures.")
        print("  Inspect failures above. Do NOT proceed to M2 until they pass.")
        print("=" * 64)
        return 1


if __name__ == "__main__":
    sys.exit(main())
