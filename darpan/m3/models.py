"""M3 database models and portable schema definitions.

The bundled SQLite implementation is production-shaped and can be mapped to
PostgreSQL using the SQLAlchemy-style table definitions below.
"""
from __future__ import annotations


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS banks (
    bank_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    bank_type TEXT NOT NULL DEFAULT 'UNKNOWN',
    rbi_short_code TEXT,
    aliases TEXT
);

CREATE TABLE IF NOT EXISTS regions (
    region_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    ombudsman_office_code TEXT
);

CREATE TABLE IF NOT EXISTS complaint_categories (
    category_id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    pre_2021_label TEXT
);

CREATE TABLE IF NOT EXISTS complaints_annual (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id TEXT,
    region_id TEXT,
    category_id TEXT,
    year TEXT NOT NULL,
    sub_type TEXT,
    received INTEGER NOT NULL CHECK(received >= 0),
    disposed INTEGER NOT NULL CHECK(disposed >= 0),
    pending_at_year_end INTEGER NOT NULL DEFAULT 0 CHECK(pending_at_year_end >= 0),
    awards_issued INTEGER NOT NULL DEFAULT 0 CHECK(awards_issued >= 0),
    award_amount REAL NOT NULL DEFAULT 0 CHECK(award_amount >= 0),
    avg_resolution_days REAL CHECK(avg_resolution_days IS NULL OR avg_resolution_days >= 0),
    source_doc_ref TEXT NOT NULL,
    source_page INTEGER NOT NULL CHECK(source_page >= 1),
    source_table INTEGER,
    extract_strategy TEXT NOT NULL,
    raw_text_excerpt TEXT,
    FOREIGN KEY (bank_id) REFERENCES banks(bank_id),
    FOREIGN KEY (region_id) REFERENCES regions(region_id),
    FOREIGN KEY (category_id) REFERENCES complaint_categories(category_id)
);

CREATE TABLE IF NOT EXISTS bank_financials (
    bank_id TEXT NOT NULL,
    year TEXT NOT NULL,
    deposits REAL,
    advances REAL,
    npa_ratio REAL,
    branch_count INTEGER,
    source_ref TEXT,
    PRIMARY KEY (bank_id, year),
    FOREIGN KEY (bank_id) REFERENCES banks(bank_id)
);

CREATE TABLE IF NOT EXISTS staging_tables (
    reporting_year TEXT NOT NULL,
    source_doc TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    table_index INTEGER,
    detected_table_kind TEXT,
    confidence TEXT,
    n_rows INTEGER,
    n_cols INTEGER,
    raw_json TEXT,
    loaded_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_complaints_year ON complaints_annual(year);
CREATE INDEX IF NOT EXISTS idx_complaints_bank_year ON complaints_annual(bank_id, year);
CREATE INDEX IF NOT EXISTS idx_complaints_category_year ON complaints_annual(category_id, year);
CREATE INDEX IF NOT EXISTS idx_complaints_region_year ON complaints_annual(region_id, year);
CREATE INDEX IF NOT EXISTS idx_complaints_source ON complaints_annual(source_doc_ref, source_page);
CREATE INDEX IF NOT EXISTS idx_financials_year ON bank_financials(year);
"""


TABLE_NAMES = (
    "banks",
    "regions",
    "complaint_categories",
    "complaints_annual",
    "bank_financials",
    "staging_tables",
)
