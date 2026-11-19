"""M2 runner: M1 tables -> staging -> normalized fact CSV + SQLite."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from transform import transform
from validate import validate


ROOT = Path(__file__).resolve().parents[1]
M1_ROOT = ROOT / "m1" / "outputs"
M0_DRIFT = ROOT / "m0" / "outputs"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def main() -> int:
    print("=" * 64)
    print("M2 — ETL & schema reconciliation")
    print("=" * 64)

    if not (M1_ROOT / "extracted").exists():
        print("ERROR: M1 output missing. Run M1 first.", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    drift_path = M0_DRIFT / "format_drift_log.json"
    drift = json.loads(drift_path.read_text()) if drift_path.exists() else {}

    summary = transform(M1_ROOT, drift, OUTPUT_DIR)

    validation = validate(
        OUTPUT_DIR / "normalized_complaints.csv",
        OUTPUT_DIR / "staging" / "staging_tables.csv",
    )
    (OUTPUT_DIR / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")

    print(f"  Staging tables:      {summary['staging_rows']}")
    print(f"  Normalized facts:    {summary['normalized_facts']}")
    print(f"  Rejected/ambiguous:  {summary['rejections']}")
    print()
    print("Outputs:")
    print(f"  {summary['staging_csv']}")
    print(f"  {summary['normalized_csv']}")
    print(f"  {summary['rejection_csv']}")
    print(f"  {summary['sqlite']}")
    print("=" * 64)

    (OUTPUT_DIR / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
