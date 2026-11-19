# M2 — ETL & Schema Reconciliation

M2 turns M1's extracted tables into append-only staging plus a normalized `complaints_annual` fact table.

## Run

```powershell
C:\Users\kshiv\AppData\Local\Programs\Python\Python310\python.exe c:\Users\kshiv\Downloads\banking\final\darpan\m2\run.py
```

## Outputs

- `outputs/staging/staging_tables.csv`
- `outputs/normalized_complaints.csv`
- `outputs/rejections.csv`
- `outputs/darpan_m2.sqlite`
- `outputs/run_summary.json`

## Design rules

1. **Staging is append-only at the table level** — every M1 table is retained with source provenance.
2. **Normalization is exact-match only** — M2 does not guess banks/categories/regions.
3. **Three era adapters** — `bos_legacy_v1`, `bos_nbfc_transition_v2`, `ios_unified_v3`.
4. **Ambiguity is rejected** — rejected rows stay in `rejections.csv` for M1/M2 fixes rather than creating false facts.
5. **Raw values remain auditable** — source PDF, page, table index, extracted year and raw row text are retained.

## Target schema

`complaints_annual`

- `bank_id`
- `category_id`
- `region_id`
- `year_id`
- `received`
- `disposed`
- `pending_at_year_end`
- `award_count`
- `award_amount_inr`
- `avg_resolution_days`
- source provenance fields

## Verified status

- 1,179 M1 staging tables preserved
- 206 normalized facts emitted
- 327 ambiguous/unsupported tables moved to rejections
- All 9 reporting years covered: 2016-17 through 2024-25
- 0 duplicate facts
- 0 negative metrics
- 0 missing source provenance

M2 is conservative: it rejects recognized tables that cannot produce exact canonical entity matches rather than inventing facts.
