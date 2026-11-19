# M0 — Data Reconnaissance & Schema Design

> Layer 0 / Foundation. 1–2 weeks. **Critical gate** — every downstream module
> depends on this audit being honest.

## What M0 delivers

| # | Deliverable | Where it lives |
|---|---|---|
| 1 | **Source inventory** across all 9 report PDFs (page count, format, metrics available) | `outputs/source_inventory.json`, `outputs/source_inventory.csv` |
| 2 | **Format drift log**: pre-2018 / 2018–2021 / post-2021 IOS schema variants documented | `outputs/format_drift_log.md`, `outputs/format_drift_log.json` |
| 3 | **Canonical entity model** on paper: `Bank`, `Category`, `Region`, `Year`, `ComplaintRecord` | [`entities.py`](./entities.py) (Pydantic v2) |
| 4 | **Extraction strategy decision** per year (native / OCR / hybrid) | `outputs/extraction_strategy_map.csv` |

## How to run

```powershell
cd c:\Users\kshiv\Downloads\banking\final\darpan\m0
python run.py
```

That's it — both stages run end-to-end and write all four artifacts to
[`outputs/`](./outputs/).

## Architecture

```
Ombudsman/*.pdf
     │
     ▼
  inspect.py   ──▶  source_inventory.{json,csv}
     │                  (page count, text-layer detection, metric sampling)
     ▼
  classify.py  ──▶  format_drift_log.{md,json}
     │                  (era + schema variant)
     ▼
                   extraction_strategy_map.csv
                   (consumed by M1 extractor)
```

## How downstream modules consume M0

- **M1 (PDF extraction engine)** reads `extraction_strategy_map.csv` to decide
  whether to call pdfplumber (native) or Tesseract/LayoutLMv3 (OCR) per PDF.
- **M2 (ETL)** reads `format_drift_log.md` to know which `schema_variant`
  parser adapter to wire up per row.
- **M3 (DB layer)** uses `entities.py` as the contract for dimension and fact
  tables.

## Why this matters

The DARPAN plan says: *"⚡ Critical gate — every downstream module depends
on this audit being honest. The format drift log prevents 80% of ETL pain.
Do not skip or rush."*

An elegant stress score on shaky extracted data = confidently wrong outputs.
M0 is the gate that makes M1–M7 trustworthy.
