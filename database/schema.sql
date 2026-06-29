-- ==========================================================
-- DARPAN DATA WAREHOUSE SCHEMA
-- RBI Integrated Ombudsman Complaint Analytics
-- ==========================================================

DROP SCHEMA IF EXISTS darpan CASCADE;
CREATE SCHEMA darpan;

SET search_path TO darpan;

-- ==========================================================
-- DIMENSION TABLES
-- ==========================================================

CREATE TABLE dim_year (
    year_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    financial_year VARCHAR(9) NOT NULL UNIQUE,
    scheme VARCHAR(20) NOT NULL,

    CONSTRAINT chk_financial_year
        CHECK (financial_year ~ '^[0-9]{4}-[0-9]{2}$'),

    CONSTRAINT chk_scheme
        CHECK (scheme IN ('BO', 'RBIOS'))
);

COMMENT ON TABLE dim_year IS
'Financial years and applicable Ombudsman scheme.';


CREATE TABLE dim_bank (
    bank_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bank_name TEXT NOT NULL UNIQUE,
    bank_type VARCHAR(50),

    CONSTRAINT chk_bank_name
        CHECK (length(trim(bank_name)) > 0)
);

COMMENT ON TABLE dim_bank IS
'Master list of regulated entities/banks.';


CREATE TABLE dim_category (
    category_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE,

    CONSTRAINT chk_category_name
        CHECK (length(trim(category_name)) > 0)
);

COMMENT ON TABLE dim_category IS
'Complaint categories published by RBI.';


CREATE TABLE dim_office (
    office_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    office_name TEXT NOT NULL UNIQUE,

    CONSTRAINT chk_office_name
        CHECK (length(trim(office_name)) > 0)
);

COMMENT ON TABLE dim_office IS
'RBI Ombudsman offices.';


CREATE TABLE dim_disposal_type (
    disposal_type_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    disposal_type TEXT NOT NULL UNIQUE,

    CONSTRAINT chk_disposal_type
        CHECK (length(trim(disposal_type)) > 0)
);

COMMENT ON TABLE dim_disposal_type IS
'Modes of complaint disposal.';

-- ==========================================================
-- FACT TABLES
-- ==========================================================

CREATE TABLE fact_category_complaints (

    fact_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    year_id INTEGER NOT NULL
        REFERENCES dim_year(year_id),

    category_id INTEGER NOT NULL
        REFERENCES dim_category(category_id),

    complaints INTEGER NOT NULL,

    percentage NUMERIC(6,2),

    source_file TEXT NOT NULL,

    load_timestamp TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    etl_version VARCHAR(20)
        DEFAULT 'v1.0',

    CONSTRAINT chk_category_complaints
        CHECK (complaints >= 0),

    CONSTRAINT chk_category_percentage
        CHECK (
            percentage IS NULL OR
            percentage BETWEEN 0 AND 100
        ),

    CONSTRAINT uq_category_year
        UNIQUE(year_id, category_id)
);

COMMENT ON TABLE fact_category_complaints IS
'Complaint counts aggregated by complaint category.';


CREATE TABLE fact_bank_complaints (

    fact_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    year_id INTEGER NOT NULL
        REFERENCES dim_year(year_id),

    bank_id INTEGER NOT NULL
        REFERENCES dim_bank(bank_id),

    complaints INTEGER NOT NULL,

    source_file TEXT NOT NULL,

    load_timestamp TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    etl_version VARCHAR(20)
        DEFAULT 'v1.0',

    CONSTRAINT chk_bank_complaints
        CHECK (complaints >= 0),

    CONSTRAINT uq_bank_year
        UNIQUE(year_id, bank_id)
);

COMMENT ON TABLE fact_bank_complaints IS
'Complaint counts aggregated by regulated entity.';


CREATE TABLE fact_office_complaints (

    fact_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    year_id INTEGER NOT NULL
        REFERENCES dim_year(year_id),

    office_id INTEGER NOT NULL
        REFERENCES dim_office(office_id),

    complaints INTEGER NOT NULL,

    source_file TEXT NOT NULL,

    load_timestamp TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    etl_version VARCHAR(20)
        DEFAULT 'v1.0',

    CONSTRAINT chk_office_complaints
        CHECK (complaints >= 0),

    CONSTRAINT uq_office_year
        UNIQUE(year_id, office_id)
);

COMMENT ON TABLE fact_office_complaints IS
'Complaint counts aggregated by Ombudsman office.';


CREATE TABLE fact_disposal (

    fact_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    year_id INTEGER NOT NULL
        REFERENCES dim_year(year_id),

    disposal_type_id INTEGER NOT NULL
        REFERENCES dim_disposal_type(disposal_type_id),

    complaints INTEGER NOT NULL,

    percentage NUMERIC(6,2),

    source_file TEXT NOT NULL,

    load_timestamp TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    etl_version VARCHAR(20)
        DEFAULT 'v1.0',

    CONSTRAINT chk_disposal_count
        CHECK (complaints >= 0),

    CONSTRAINT chk_disposal_percentage
        CHECK (
            percentage IS NULL OR
            percentage BETWEEN 0 AND 100
        ),

    CONSTRAINT uq_disposal_year
        UNIQUE(year_id, disposal_type_id)
);

COMMENT ON TABLE fact_disposal IS
'Complaint disposal statistics.';

-- ==========================================================
-- ETL AUDIT
-- ==========================================================

CREATE TABLE etl_run (

    run_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_file TEXT NOT NULL,

    financial_year VARCHAR(9),

    extracted_rows INTEGER,

    loaded_rows INTEGER,

    status VARCHAR(30),

    error_message TEXT,

    started_at TIMESTAMP,

    completed_at TIMESTAMP
);

COMMENT ON TABLE etl_run IS
'Tracks ETL execution history and status.';

-- ==========================================================
-- PERFORMANCE INDEXES
-- ==========================================================

CREATE INDEX idx_fact_category_year
ON fact_category_complaints(year_id);

CREATE INDEX idx_fact_category_category
ON fact_category_complaints(category_id);

CREATE INDEX idx_fact_category_year_category
ON fact_category_complaints(year_id, category_id);


CREATE INDEX idx_fact_bank_year
ON fact_bank_complaints(year_id);

CREATE INDEX idx_fact_bank_bank
ON fact_bank_complaints(bank_id);

CREATE INDEX idx_fact_bank_year_bank
ON fact_bank_complaints(year_id, bank_id);


CREATE INDEX idx_fact_office_year
ON fact_office_complaints(year_id);

CREATE INDEX idx_fact_office_office
ON fact_office_complaints(office_id);

CREATE INDEX idx_fact_office_year_office
ON fact_office_complaints(year_id, office_id);


CREATE INDEX idx_fact_disposal_year
ON fact_disposal(year_id);

CREATE INDEX idx_fact_disposal_type
ON fact_disposal(disposal_type_id);

CREATE INDEX idx_fact_disposal_year_type
ON fact_disposal(year_id, disposal_type_id);

-- ==========================================================
-- END OF SCHEMA
-- ==========================================================