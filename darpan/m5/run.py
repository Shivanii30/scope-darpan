"""M5 runner."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import WEIGHTS, StressEngine


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "m3" / "outputs" / "darpan.sqlite"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(path: Path, rows: list[dict]) -> None:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE stress_scores (
            bank_id TEXT PRIMARY KEY,
            bank_name TEXT NOT NULL,
            bank_type TEXT NOT NULL,
            year TEXT NOT NULL,
            complaint_intensity REAL,
            trend_velocity REAL,
            resolution_quality REAL,
            award_severity REAL,
            concentration_risk REAL,
            composite_score REAL,
            available_components INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            evidence TEXT NOT NULL
        )
    """)
    con.executemany("""
        INSERT INTO stress_scores VALUES (
            :bank_id,:bank_name,:bank_type,:year,:complaint_intensity,
            :trend_velocity,:resolution_quality,:award_severity,
            :concentration_risk,:composite_score,:available_components,
            :confidence,:evidence
        )
    """, rows)
    con.commit()
    con.close()


def validate(rows: list[dict]) -> dict:
    errors: list[str] = []
    for row in rows:
        composite = row["composite_score"]
        if composite is not None and not (0 <= composite <= 100):
            errors.append(f"{row['bank_id']} composite outside 0-100")
        for key in ("complaint_intensity", "trend_velocity", "resolution_quality", "award_severity", "concentration_risk"):
            value = row[key]
            if value is not None and not (0 <= value <= 100):
                errors.append(f"{row['bank_id']} {key} outside 0-100")
        if row["available_components"] > 5:
            errors.append(f"{row['bank_id']} invalid component count")

    return {
        "ok": not errors,
        "errors": errors,
        "bank_scores": len(rows),
        "high_confidence": sum(r["confidence"] == "high" for r in rows),
        "medium_confidence": sum(r["confidence"] == "medium" for r in rows),
        "low_confidence": sum(r["confidence"] == "low" for r in rows),
        "weights": WEIGHTS,
    }


def main() -> int:
    print("=" * 64)
    print("M5 — Stress score engine")
    print("=" * 64)

    if not DB_PATH.exists():
        print(f"ERROR: M3 database missing: {DB_PATH}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = StressEngine(DB_PATH)
    rows = engine.run()
    bank_financials_available = engine.bank_financials_available()
    engine.close()

    write_csv(OUTPUT_DIR / "stress_scores.csv", rows)
    write_sqlite(OUTPUT_DIR / "stress_scores.sqlite", rows)

    validation = validate(rows)
    summary = {
        "database": str(DB_PATH),
        "weights": WEIGHTS,
        "bank_financials_available": bank_financials_available,
        "validation": validation,
    }
    (OUTPUT_DIR / "m5_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"  Banks scored: {len(rows)}")
    print(f"  High confidence: {validation['high_confidence']}")
    print(f"  Medium confidence: {validation['medium_confidence']}")
    print(f"  Low confidence: {validation['low_confidence']}")
    print(f"  Validation: {'PASS' if validation['ok'] else 'FAIL'}")
    print("=" * 64)

    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
