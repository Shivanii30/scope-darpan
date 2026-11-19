"""M6 runner."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import AnomalyEngine


ROOT = Path(__file__).resolve().parents[1]
M3_DB = ROOT / "m3" / "outputs" / "darpan.sqlite"
M5_DB = ROOT / "m5" / "outputs" / "stress_scores.sqlite"
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
        CREATE TABLE anomalies (
            bank_id TEXT,
            bank_name TEXT,
            bank_type TEXT,
            year TEXT,
            category TEXT,
            method TEXT,
            anomaly_score REAL,
            z_score REAL,
            baseline_mean REAL,
            observed_value REAL,
            severity TEXT,
            reason TEXT,
            source_context TEXT
        )
    """)
    con.execute("CREATE INDEX idx_anomalies_bank ON anomalies(bank_id)")
    con.execute("CREATE INDEX idx_anomalies_year ON anomalies(year)")
    con.execute("CREATE INDEX idx_anomalies_category ON anomalies(category)")
    con.executemany("""
        INSERT INTO anomalies VALUES (
            :bank_id,:bank_name,:bank_type,:year,:category,:method,
            :anomaly_score,:z_score,:baseline_mean,:observed_value,
            :severity,:reason,:source_context
        )
    """, rows)
    con.commit()
    con.close()


def validate(rows: list[dict]) -> dict:
    errors: list[str] = []
    valid_severity = {"low", "medium", "high"}
    valid_methods = {"rolling_z_score", "mean_shift_change_point", "rolling_z_score_category"}

    for row in rows:
        if row["severity"] not in valid_severity:
            errors.append(f"invalid severity: {row['severity']}")
        if row["method"] not in valid_methods:
            errors.append(f"invalid method: {row['method']}")
        if not row["bank_id"] or not row["year"] or not row["reason"]:
            errors.append("missing anomaly identity or reason")

    by_method: dict[str, int] = {}
    for row in rows:
        by_method[row["method"]] = by_method.get(row["method"], 0) + 1

    return {
        "ok": not errors,
        "errors": errors,
        "anomalies": len(rows),
        "by_method": by_method,
    }


def main() -> int:
    print("=" * 64)
    print("M6 — Anomaly detection engine")
    print("=" * 64)

    missing = [p for p in (M3_DB, M5_DB) if not p.exists()]
    if missing:
        print("ERROR: M5/M3 database missing", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = AnomalyEngine(M3_DB, M5_DB)
    rows = engine.detect()
    engine.close()

    write_csv(OUTPUT_DIR / "anomalies.csv", rows)
    write_sqlite(OUTPUT_DIR / "anomalies.sqlite", rows)

    validation = validate(rows)
    summary = {
        "m3_database": str(M3_DB),
        "m5_database": str(M5_DB),
        "validation": validation,
        "methods": ["rolling_z_score", "mean_shift_change_point", "rolling_z_score_category"],
        "not_implemented": ["stl_seasonal_decomposition", "ruptures_change_point", "isolation_forest"],
    }
    (OUTPUT_DIR / "m6_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"  Anomalies: {len(rows)}")
    print(f"  Methods: {', '.join(validation['by_method'])}")
    print(f"  Validation: {'PASS' if validation['ok'] else 'FAIL'}")
    print("=" * 64)
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
