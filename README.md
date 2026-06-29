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

## Data Sources and PDF Extraction

### RBI Ombudsman Annual Reports (2016–17 to 2024–25)

Extracted information includes:

* Bank-wise complaints
* Category-wise complaints
* Office-wise complaints
* Disposal statistics

### DBIE Banking Indicators

* Gross NPA
* Credit Growth
* Digital Payment Indicators
* Other supervisory metrics

---

### Targeted PDF Extraction

Instead of extracting every table from every report, the extraction pipeline targets only the required supervisory tables.

Categories extracted:

* Bank-wise complaints
* Category-wise complaints
* Office-wise complaints
* Disposal statistics

<img width="1024" height="559" alt="image" src="https://github.com/user-attachments/assets/7a81cbca-768d-43e5-9c77-0f74b481cad9" />


---

## Technologies

* Python
* Camelot
* pdfplumber
* pandas

---

