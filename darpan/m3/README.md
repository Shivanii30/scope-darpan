# M3 — Database Layer

M3 loads M2's normalized facts and staging tables into a portable, indexed SQLite database.

## Run

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m3\run.py
```

## Output

- `outputs/darpan.sqlite` — working database
- `outputs/m3_summary.json` — load and validation report

## Tables

- `banks`
- `regions`
- `complaint_categories`
- `complaints_annual`
- `bank_financials`
- `staging_tables`

## Validation

M3 verifies:

- all 9 reporting years exist
- no negative complaint or award metrics
- every fact has source document and page provenance
- no duplicate facts
- staging and fact counts are loaded

## PostgreSQL migration

The SQLite DDL and loader are intentionally schema-compatible with PostgreSQL. A later migration can replace SQLite with PostgreSQL while retaining table and column names.

For production deployment, route dashboard reads to a read replica and use `read_replica_style_query()` for aggregate reads.
