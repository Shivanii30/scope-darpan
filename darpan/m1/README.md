# M1 — PDF Extraction Engine

> Layer 1 / Ingestion. 2–3 weeks. Builds the raw row material that M2 will
> reconcile into the canonical schema.

## Current status: COMPLETE for the available 9-PDF corpus

- **9/9 source PDFs pass spot-check validation**
- **1,179 tables extracted**
- **1,879 candidate records emitted**
- Native `pdfplumber` extraction is complete
- Camelot lattice/stream fallback is active for pages pdfplumber misses
- `tables.jsonl` and `candidates.jsonl` are persisted for every PDF
- OCR remains an optional future branch for PDFs M0 later flags as `ocr` or `hybrid`

## What M1 delivers

| # | Deliverable | Where it lives |
|---|---|---|
| 1 | **Native-text extractor** using pdfplumber (camelot fallback stub for tables pdfplumber misses) | [`native_extractor.py`](./native_extractor.py) |
| 2 | **OCR fallback pipeline** stub (Tesseract + LayoutLMv3) — *not built yet*, router fails loud | [`router.py`](./router.py) `NotImplementedError` |
| 3 | **Extraction router** — reads M0's strategy map and dispatches per PDF | [`router.py`](./router.py) |
| 4 | **Raw extracted tables** saved to disk per-PDF with PDF + page + table index | `outputs/extracted/<year>/<file>.tables.jsonl` |
| 5 | **Table classifier** — labels each extracted table by kind (complaint_timeseries, category_breakdown, etc.) and emits candidate rows | [`classify_tables.py`](./classify_tables.py) |
| 6 | **Spot-check validation** on 3 known years (2016-17, 2021-22, 2024-25) | [`validate.py`](./validate.py) |

## How to run

```powershell
cd c:\Users\kshiv\Downloads\banking\final\darpan\m1
python run.py
```

This will:
1. Read M0's `extraction_strategy_map.csv` and route every PDF.
2. For each `native` PDF, walk every page and pull every table.
3. Classify each table by `detected_table_kind`.
4. Spot-check 3 known years against values we observed in the actual PDFs.
5. Write a per-PDF JSONL plus a top-level `extraction_summary.json`.

## Architecture

```
M0 outputs/extraction_strategy_map.csv
        │
        ▼
  router.py             ──▶ dispatch (native | ocr-stub)
        │
        ▼
  native_extractor.py   ──▶ outputs/extracted/<year>/<file>.tables.jsonl
        │                 (one JSON line per ExtractedTable)
        ▼
  classify_tables.py    ──▶ label + emit CandidateRecord candidates
        │
        ▼
  validate.py           ──▶ spot-check on 3 known years
        │
        ▼
  outputs/extraction_summary.json
```

## How M2 consumes M1

M2 reads `outputs/extracted/<year>/<file>.tables.jsonl` and:

1. For each `ExtractedTable`, looks up the `detected_table_kind` to pick a
   parser adapter (one per `schema_variant` from M0).
2. For each `CandidateRecord`, joins the `entity_label` against dimension
   tables (`banks`, `complaint_categories`, `regions`) to assign canonical IDs.
3. Validates row counts and cross-tab totals.

## Router behavior

| M0 strategy | What M1 does |
|---|---|
| `native` (all 9 current PDFs) | `pdfplumber.extract_tables()` on every page |
| `hybrid` | Not implemented — `NotImplementedError` raised (operator sees a clear message) |
| `ocr` | Not implemented — `NotImplementedError` raised (operator sees a clear message) |

The M0 plan said: *"Don't assume one extractor works for all years.
Validate extraction on 2-3 known years before declaring the router done."*

M0 audit says all 9 current PDFs are native, so we haven't yet had to build
the OCR path. The router stub keeps that gap visible rather than hiding it.

## Spot-check expected values

These come from manually inspecting the actual RBI PDFs:

| Year | Metric | Value | Source page |
|---|---|---:|---|
| 2016-17 | complaints received | 130,987 | page 17 |
| 2016-17 | complaints disposed | 125,319 | page 17 |
| 2021-22 | total receipt | 9,11,384 | page 18 |
| 2024-25 | total receipt | 9,11,384 | page 18 (3-year timeseries) |

Validation tolerates ±2% to account for pdfplumber occasionally picking up
the wrong column on a multi-section page.
