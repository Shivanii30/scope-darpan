"""M3 database setup and loader."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from models import DDL
from dimensions import BANKS, CATEGORIES, REGIONS


class DarpanDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.con = sqlite3.connect(db_path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")

    def close(self):
        self.con.close()

    def migrate(self):
        self.con.executescript(DDL)
        self.con.commit()

    def seed_dimensions(self):
        self.con.executemany(
            "INSERT OR IGNORE INTO banks(bank_id, canonical_name, bank_type, rbi_short_code, aliases) VALUES(?,?,?,?,?)",
            BANKS,
        )
        self.con.executemany(
            "INSERT OR IGNORE INTO complaint_categories(category_id, code, label, pre_2021_label) VALUES(?,?,?,?)",
            CATEGORIES,
        )
        self.con.executemany(
            "INSERT OR IGNORE INTO regions(region_id, city, state, ombudsman_office_code) VALUES(?,?,?,?)",
            REGIONS,
        )
        self.con.commit()

    def load_m2(self, normalized_csv: Path, staging_csv: Path, rejections_csv: Path):
        self.con.execute("DELETE FROM complaints_annual")
        self.con.execute("DELETE FROM staging_tables")

        loaded_facts = 0
        with normalized_csv.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                self.con.execute("""
                    INSERT INTO complaints_annual (
                        bank_id, region_id, category_id, year, sub_type,
                        received, disposed, pending_at_year_end, awards_issued,
                        award_amount, avg_resolution_days, source_doc_ref,
                        source_page, source_table, extract_strategy, raw_text_excerpt
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    row["bank_id"] or None,
                    row["region_id"] or None,
                    row["category_id"] or None,
                    row["year_id"],
                    None,
                    int(row["received"] or 0),
                    int(row["disposed"] or 0),
                    int(row["pending_at_year_end"] or 0),
                    int(row["award_count"] or 0),
                    float(row["award_amount_inr"] or 0),
                    float(row["avg_resolution_days"]) if row["avg_resolution_days"] else None,
                    row["source_doc"],
                    int(row["page_number"]),
                    int(row["table_index"]) if row["table_index"] else None,
                    row["extract_strategy"],
                    row["raw_text_excerpt"],
                ))
                loaded_facts += 1

        loaded_staging = 0
        with staging_csv.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                self.con.execute("""
                    INSERT INTO staging_tables (
                        reporting_year, source_doc, page_number, table_index,
                        detected_table_kind, confidence, n_rows, n_cols, raw_json,
                        loaded_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
                """, (
                    row["reporting_year"], row["source_doc"], int(row["page_number"]),
                    int(row["table_index"]) if row["table_index"] else None,
                    row["detected_table_kind"], row["confidence"],
                    int(row["n_rows"]), int(row["n_cols"]), row["raw_json"],
                ))
                loaded_staging += 1

        self.con.commit()
        return {"facts": loaded_facts, "staging": loaded_staging}

    def validate(self) -> dict:
        fact_count = self.con.execute("SELECT COUNT(*) FROM complaints_annual").fetchone()[0]
        staging_count = self.con.execute("SELECT COUNT(*) FROM staging_tables").fetchone()[0]
        years = [r[0] for r in self.con.execute("SELECT DISTINCT year FROM complaints_annual ORDER BY year")]
        negative = self.con.execute("SELECT COUNT(*) FROM complaints_annual WHERE received < 0 OR disposed < 0 OR pending_at_year_end < 0 OR awards_issued < 0 OR award_amount < 0").fetchone()[0]
        missing_source = self.con.execute("SELECT COUNT(*) FROM complaints_annual WHERE source_doc_ref IS NULL OR source_doc_ref='' OR source_page < 1").fetchone()[0]
        duplicate_count = self.con.execute("""
            SELECT COUNT(*) FROM (
                SELECT bank_id, category_id, region_id, year, received, disposed,
                       source_doc_ref, source_page, COUNT(*) AS n
                FROM complaints_annual
                GROUP BY bank_id, category_id, region_id, year, received, disposed,
                         source_doc_ref, source_page
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        return {
            "ok": negative == 0 and missing_source == 0 and duplicate_count == 0 and len(years) == 9,
            "facts": fact_count,
            "staging": staging_count,
            "years": years,
            "negative_metrics": negative,
            "missing_source": missing_source,
            "duplicate_facts": duplicate_count,
        }

    def read_replica_style_query(self, year: str):
        """Read-only-style aggregate query intended for dashboard traffic."""
        return self.con.execute("""
            SELECT b.canonical_name, c.label,
                   SUM(a.received) AS received,
                   SUM(a.disposed) AS disposed,
                   SUM(a.pending_at_year_end) AS pending,
                   SUM(a.awards_issued) AS awards
            FROM complaints_annual a
            LEFT JOIN banks b ON b.bank_id = a.bank_id
            LEFT JOIN complaint_categories c ON c.category_id = a.category_id
            WHERE a.year = ?
            GROUP BY b.canonical_name, c.label
            ORDER BY received DESC
        """, (year,)).fetchall()
