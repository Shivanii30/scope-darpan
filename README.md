# DARPAN

### Diagnostic Analytics & Regulatory Pattern Awareness Network

DARPAN is a data engineering and analytics project that consolidates complaint data from the Reserve Bank of India (RBI) Ombudsman reports, public complaint datasets, and banking sector indicators into a unified analytical platform.

The goal is to build a clean, reproducible ETL pipeline that enables regulatory analytics, complaint trend analysis, and banking supervision insights.

---

## Project Objectives

* Build an automated data ingestion pipeline for RBI Ombudsman reports.
* Extract structured complaint statistics from annual PDF reports.
* Integrate complaint datasets with banking sector indicators.
* Standardize historical data across multiple reporting formats.
* Create datasets suitable for downstream analytics and visualization.

---

## Data Sources

### RBI Ombudsman Annual Reports (2016–17 to 2024–25)

Extracted information includes:

* Bank-wise complaints
* Category-wise complaints
* Office-wise complaints
* Disposal statistics

### data.gov.in Complaint Datasets

* Complaint statistics
* Category-wise complaints
* Office-wise complaints
* Bank-wise complaints

### DBIE Banking Indicators

* Gross NPA
* Credit Growth
* Digital Payment Indicators
* Other supervisory metrics

---

## Project Structure

```text
darpan/
│
├── data/
│   ├── raw/              # Source PDFs and downloaded datasets (ignored)
│   ├── extracted/        # Generated CSVs (ignored)
│   └── sample/           # Optional sample outputs
│
├── extract_tables.py
├── table_map.json
├── requirements.txt
├── README.md
└── .gitignore
```

---

# Phase 1 — Data Inventory & PDF Extraction ✅

Completed

### Data Inventory

* Collected RBI Ombudsman Annual Reports
* Collected public complaint datasets
* Collected DBIE banking indicators
* Documented reporting years and available tables

### Targeted PDF Extraction

Instead of extracting every table from every report, the extraction pipeline targets only the required supervisory tables.

Categories extracted:

* Bank-wise complaints
* Category-wise complaints
* Office-wise complaints
* Disposal statistics

### Extraction Workflow

```
PDF
    │
    ▼
Read Table of Contents
    │
    ▼
Locate target table using table_map.json
    │
    ▼
Convert printed page → PDF page
    │
    ▼
Extract table using Camelot
    │
    ▼
Export CSV
```

---

## Technologies

* Python
* Camelot
* pdfplumber
* pandas

---

# Upcoming Work

## Phase 2 — ETL Pipeline

* Clean extracted tables
* Standardize schemas across years
* Normalize bank and office names
* Handle reporting format changes
* Merge annual datasets
* Validate extracted values against data.gov.in

## Phase 3 — Data Warehouse

* Design analytical schema
* Load cleaned datasets into PostgreSQL
* Create reusable data models

## Phase 4 — Analytics

* Complaint trends
* Bank benchmarking
* Office performance analysis
* Complaint disposal efficiency
* Regulatory dashboards

---

## Status

| Phase          | Status     |
| -------------- | ---------- |
| Data Inventory | ✅ Complete |
| PDF Extraction | ✅ Complete |
| ETL Pipeline   | 🚧 Next    |
| Data Warehouse | Planned    |
| Analytics      | Planned    |
