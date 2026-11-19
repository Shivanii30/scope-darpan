"""M2 staging and normalized transform."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from adapters import adapt_table


def iter_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def transform(m1_root: Path, m0_drift: dict, output_dir: Path) -> dict:
    staging_dir = output_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    staging_rows: list[dict] = []
    normalized: list[dict] = []
    rejections: list[dict] = []

    variant_by_year = {
        row["reporting_year"]: row["schema_variant"]
        for row in json.loads((m1_root.parents[1] / "m0" / "outputs" / "format_drift_log.json").read_text()).get("per_pdf", [])
    }

    for tables_path in sorted((m1_root / "extracted").glob("*/*/tables.jsonl")):
        year_dir = tables_path.parent.parent.name
        for table in iter_jsonl(tables_path):
            staging_rows.append({
                "reporting_year": year_dir,
                "source_doc": table["source"]["source_doc"],
                "page_number": table["source"]["page_number"],
                "table_index": table["source"].get("table_index"),
                "detected_table_kind": table["detected_table_kind"],
                "confidence": table["confidence"],
                "n_rows": table["n_rows"],
                "n_cols": table["n_cols"],
                "raw_json": json.dumps(table, ensure_ascii=False),
            })

            variant = variant_by_year.get(year_dir)
            if not variant:
                rejections.append({"year": year_dir, "source_doc": table["source"]["source_doc"],
                                   "reason": "missing M0 schema variant", "page": table["source"]["page_number"]})
                continue

            facts = adapt_table(table, year_dir, variant)
            if table["detected_table_kind"] not in ("unknown", "toc") and not facts:
                rejections.append({"year": year_dir, "source_doc": table["source"]["source_doc"],
                                   "reason": "recognized table produced no exact dimension match",
                                   "page": table["source"]["page_number"],
                                   "kind": table["detected_table_kind"]})
            normalized.extend(facts)

    # Deduplicate exact fact rows; provenance remains a separate staging row.
    dedup: dict[tuple, dict] = {}
    for fact in normalized:
        key = (fact["bank_id"], fact["category_id"], fact["region_id"], fact["year_id"],
               fact["received"], fact["disposed"], fact["source_doc"], fact["page_number"])
        dedup[key] = fact
    normalized = list(dedup.values())

    staging_csv = staging_dir / "staging_tables.csv"
    write_csv(staging_csv, staging_rows)

    normalized_csv = output_dir / "normalized_complaints.csv"
    write_csv(normalized_csv, normalized)

    rejection_csv = output_dir / "rejections.csv"
    write_csv(rejection_csv, rejections)

    db_path = output_dir / "darpan_m2.sqlite"
    create_sqlite(db_path, staging_rows, normalized)

    return {
        "staging_rows": len(staging_rows),
        "normalized_facts": len(normalized),
        "rejections": len(rejections),
        "staging_csv": str(staging_csv),
        "normalized_csv": str(normalized_csv),
        "rejection_csv": str(rejection_csv),
        "sqlite": str(db_path),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def create_sqlite(db_path: Path, staging: list[dict], normalized: list[dict]) -> None:
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript("""
    CREATE TABLE staging_tables (
      reporting_year TEXT, source_doc TEXT, page_number INTEGER, table_index INTEGER,
      detected_table_kind TEXT, confidence TEXT, n_rows INTEGER, n_cols INTEGER, raw_json TEXT
    );
    CREATE TABLE complaints_annual (
      bank_id TEXT, category_id TEXT, region_id TEXT, year_id TEXT,
      received INTEGER, disposed INTEGER, pending_at_year_end INTEGER,
      award_count INTEGER, award_amount_inr REAL, avg_resolution_days REAL,
      source_doc TEXT, page_number INTEGER, table_index INTEGER,
      extract_strategy TEXT, raw_text_excerpt TEXT
    );
    CREATE TABLE rejections (
      reporting_year TEXT, source_doc TEXT, page_number INTEGER, reason TEXT, kind TEXT
    );
    """)
    con.executemany("INSERT INTO staging_tables VALUES (:reporting_year,:source_doc,:page_number,:table_index,:detected_table_kind,:confidence,:n_rows,:n_cols,:raw_json)", staging)
    con.executemany("INSERT INTO complaints_annual VALUES (:bank_id,:category_id,:region_id,:year_id,:received,:disposed,:pending_at_year_end,:award_count,:award_amount_inr,:avg_resolution_days,:source_doc,:page_number,:table_index,:extract_strategy,:raw_text_excerpt)", normalized)
    con.commit()
    con.close()
