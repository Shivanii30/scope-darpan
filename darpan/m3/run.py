"""M3 database runner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import DarpanDB


ROOT = Path(__file__).resolve().parents[1]
M2_OUTPUT = ROOT / "m2" / "outputs"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def main() -> int:
    print("=" * 64)
    print("M3 — Database layer")
    print("=" * 64)

    normalized = M2_OUTPUT / "normalized_complaints.csv"
    staging = M2_OUTPUT / "staging" / "staging_tables.csv"
    rejections = M2_OUTPUT / "rejections.csv"

    missing = [str(p) for p in (normalized, staging, rejections) if not p.exists()]
    if missing:
        print("ERROR: M2 outputs missing:", file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        print("Run M2 first.", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = OUTPUT_DIR / "darpan.sqlite"
    db = DarpanDB(db_path)
    db.migrate()
    db.seed_dimensions()
    loaded = db.load_m2(normalized, staging, rejections)
    validation = db.validate()
    db.close()

    summary = {
        "database": str(db_path),
        "loaded": loaded,
        "validation": validation,
        "rejections_source": str(rejections),
        "tables": ["banks", "regions", "complaint_categories", "complaints_annual", "bank_financials", "staging_tables"],
    }

    (OUTPUT_DIR / "m3_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"  Database: {db_path}")
    print(f"  Facts loaded: {loaded['facts']}")
    print(f"  Staging loaded: {loaded['staging']}")
    print(f"  Years: {', '.join(validation['years'])}")
    print(f"  Validation: {'PASS' if validation['ok'] else 'FAIL'}")
    print("=" * 64)

    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
