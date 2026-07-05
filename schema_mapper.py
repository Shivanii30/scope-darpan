"""
schema_mapper.py
────────────────
Takes classified_tables.json → maps every table to the production schema.

Pipeline:
  1. Sub-classify (10 sub-types) using heuristic rules + Qwen fallback
  2. Extract: per-sub-type parsers build normalised records
  3. Deduplicate: banks, regions, categories merged across all 9 PDFs
  4. Output: JSON per schema table + DDL SQL + load script

Usage:
  python schema_mapper.py                          # defaults
  python schema_mapper.py --input output/classified_tables.json
  python schema_mapper.py --no-llm                # skip Qwen fallback (faster)
  python schema_mapper.py --output schema_out

Dependencies:  pip install requests
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

# ─── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_BASE   = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"

# ─── Standard category canonical names ───────────────────────────────────────

CATEGORY_CANONICAL: dict[str, str] = {
    "atm / debit":               "ATM/Debit Cards",
    "atm/debit":                 "ATM/Debit Cards",
    "atm/dc":                    "ATM/Debit Cards",
    "atm ":                      "ATM/Debit Cards",
    "debit card":                "ATM/Debit Cards",
    "mobile":                    "Mobile/Electronic Banking",
    "electronic bank":           "Mobile/Electronic Banking",
    "internet banking":          "Mobile/Electronic Banking",
    "credit card":               "Credit Cards",
    "loans and advance":         "Loans and Advances",
    "loans and adv":             "Loans and Advances",
    "pension":                   "Pension Payments",
    "deposit account":           "Deposit Accounts",
    "remittance":                "Remittances",
    "levy of charges":           "Levy of Charges Without Prior Notice",
    "failure to meet":           "Failure to Meet Commitments",
    "non-observance of fpc":     "Non-Observance of FPC",
    "non-adherence to fair":     "Non-Observance of FPC",
    "bcsbi":                     "Non-Adherence to BCSBI Codes",
    "para banking":              "Para Banking",
    "notes and coin":            "Notes and Coins",
    "out of purview":            "Out of Purview",
    "dsa":                       "DSAs and Recovery Agents",
    "mis-selling":               "Mis-selling",
    "insurance":                 "Insurance",
    "others":                    "Others",
}

# ─── Bank type group-header keywords ─────────────────────────────────────────

BANK_TYPE_HEADERS: dict[str, str] = {
    "public sector":    "PSU",
    "nationalised":     "PSU",
    "state bank":       "PSU",
    "private sector":   "Private",
    "new private":      "Private",
    "old private":      "Private",
    "foreign":          "Foreign",
    "rrb":              "RRB",
    "regional rural":   "RRB",
    "cooperative":      "Cooperative",
    "urban co-op":      "Cooperative",
    "small finance":    "SFB",
    " sfb":             "SFB",
    "payment bank":     "Payment Bank",
    "nbfc":             "NBFC",
}

# ─── OBO city → zone ─────────────────────────────────────────────────────────

OBO_ZONES: dict[str, str] = {
    "chandigarh":            "North",
    "new delhi":             "North",
    "delhi":                 "North",
    "lucknow":               "North",
    "jaipur":                "North",
    "dehradun":              "North",
    "jammu":                 "North",
    "kanpur":                "North",
    "shimla":                "North",
    "mumbai":                "West",
    "ahmedabad":             "West",
    "pune":                  "West",
    "nagpur":                "West",
    "raipur":                "West",
    "kolkata":               "East",
    "patna":                 "East",
    "bhubaneswar":           "East",
    "guwahati":              "East",
    "ranchi":                "East",
    "siliguri":              "East",
    "chennai":               "South",
    "hyderabad":             "South",
    "bengaluru":             "South",
    "bangalore":             "South",
    "thiruvananthapuram":    "South",
    "kochi":                 "South",
    "bhopal":                "Central",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_num(val) -> Optional[float]:
    """'1,23,456' → 123456.0  |  '17.40%' → None (percentages filtered later)."""
    s = str(val).strip().replace(",", "").replace("*", "").rstrip("%")
    if not s or s in ("-", "–", "N/A", "NA"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_year(text: str) -> list[str]:
    return re.findall(r"\b(20\d{2}[-–]\d{2,4})\b", str(text))


def row_text(row: list) -> str:
    return " ".join(str(c).strip().lower() for c in row if str(c).strip())


def first_nonempty_idx(row: list) -> int:
    for i, c in enumerate(row):
        if str(c).strip():
            return i
    return 0


def detect_n_header_rows(data: list) -> int:
    """Guess how many rows form the header block (1 or 2)."""
    if len(data) < 2:
        return 1
    empty0 = sum(1 for c in data[0] if not str(c).strip())
    empty1 = sum(1 for c in data[1] if not str(c).strip())
    # Second row fills gaps left by first → 2-row header
    if len(data[0]) > 2 and empty0 > len(data[0]) * 0.35 and empty1 < empty0:
        return 2
    return 1


def merge_header_rows(rows: list, n: int) -> list[str]:
    """Merge n header rows into single column name strings."""
    cols = max(len(r) for r in rows[:n]) if rows else 0
    headers = []
    for c in range(cols):
        parts = []
        for r in range(min(n, len(rows))):
            val = str(rows[r][c]).strip().replace("\n", " ") if c < len(rows[r]) else ""
            if val and val not in parts:
                parts.append(val)
        headers.append(" ".join(parts).strip())
    return headers


def col_year_map(headers: list[str]) -> dict[int, str]:
    """Map column index → fiscal year string extracted from the header."""
    result = {}
    for i, h in enumerate(headers):
        yrs = extract_year(h)
        if yrs:
            result[i] = yrs[0]
    return result


def canonicalise_category(raw: str) -> str:
    rl = raw.lower()
    for kw, canon in CATEGORY_CANONICAL.items():
        if kw in rl:
            return canon
    return raw.strip()


def infer_zone(name: str) -> str:
    nl = name.lower()
    for city, zone in OBO_ZONES.items():
        if city in nl:
            return zone
    return "Unknown"


def is_percentage_row(row: list) -> bool:
    """Returns True if the row's numeric values look like percentages (<= 100)."""
    nums = [clean_num(c) for c in row if str(c).strip()]
    nums = [n for n in nums if n is not None]
    if not nums:
        return False
    return all(n <= 100.0 for n in nums)

# ─── Sub-type heuristic classifier ───────────────────────────────────────────

def heuristic_subtype(t: dict) -> str:
    data  = t.get("data", [])
    if not data:
        return "skip"

    header = " ".join(row_text(r) for r in data[:3])
    pctx   = t.get("_page_text", "").lower()[:400]
    full   = header + " " + pctx
    rows, cols = t.get("rows", 0), t.get("cols", 0)

    # ── Skip: TOC / index tables ─────────────────────────────────────────
    toc_kw = {"page no", "appendix no", "table no", "chart no",
               "box no", "annexure no", "nomenclature"}
    if sum(1 for k in toc_kw if k in full) >= 2:
        return "skip"
    if rows < 3 or cols < 2:
        return "skip"

    # ── fact_bank_category: individual bank × many category columns ──────
    if "name of the bank" in full and cols > 8:
        return "fact_bank_category"

    # ── fact_bank_group: bank group summary rows ─────────────────────────
    if "bank group" in full and "public sector" in full and 3 <= cols <= 12:
        return "fact_bank_group"

    # ── fact_bank_disposal: per-bank maintainable/awards/disposed ────────
    disposal_col_kw = ["maintainable", "disposed", "award", "implemented", "unimplemented"]
    bank_id_kw      = ["name of the bank", "public sector", "private sector"]
    if any(k in full for k in disposal_col_kw) and any(k in full for k in bank_id_kw):
        return "fact_bank_disposal"

    # ── fact_appeals ─────────────────────────────────────────────────────
    if "appeal" in full and ("obo" in full or "ombudsman office" in full):
        return "fact_appeals"

    # ── fact_costs ───────────────────────────────────────────────────────
    if "cost of handling" in full or ("total cost" in full and "obo" in full):
        return "fact_costs"

    # ── fact_region_complaints: rows = OBO offices / cities ──────────────
    region_kw = ["name of the obo", "name of the odto", "name of the nbfco",
                 "ombudsman office", "obo", "oodt", "onbfco"]
    city_kw   = ["chandigarh", "mumbai", "hyderabad", "kolkata", "bengaluru",
                 "chennai", "ahmedabad", "delhi", "lucknow", "patna", "bhubaneswar"]
    region_hit = any(k in full for k in region_kw)
    city_hit   = sum(1 for c in city_kw if c in full) >= 2
    if region_hit or city_hit:
        if "award" in full and "implemented" in full:
            return "fact_bank_disposal"
        if "appeal" in full:
            return "fact_appeals"
        return "fact_region_complaints"

    # ── fact_category_totals: category names in first column ─────────────
    cat_kw = ["complaint category", "nature of complaint", "sub-category",
              "atm", "credit card", "mobile banking", "loans and advance",
              "ground", "complaint category"]
    if sum(1 for k in cat_kw if k in full) >= 1 and cols >= 3:
        # Make sure first column is a category label, not a bank
        first_col = str(data[1][0] if len(data) > 1 else data[0][0]).lower()
        if any(k in first_col for k in ["atm", "credit", "mobile", "loan", "deposit",
                                         "pension", "remit", "category", "ground"]):
            return "fact_category_totals"

    # ── fact_disposal_modes: how complaints were disposed ────────────────
    mode_kw = ["mutual settlement", "mode of disposal", "disposed by", "rejected",
               "ground for rejection", "non-maintainable", "not on grounds",
               "first resort", "particulars", "by award", "by mutual"]
    if sum(1 for k in mode_kw if k in full) >= 1:
        return "fact_disposal_modes"

    return "skip"


# ─── LLM fallback (Qwen2.5:3b via Ollama) ────────────────────────────────────

def llm_subtype(t: dict, model: str) -> str:
    """Ask Qwen for sub-type when heuristic isn't confident."""
    data = t.get("data", [])
    hdr  = "\n".join(
        " | ".join(str(c).strip()[:25] for c in r if str(c).strip())
        for r in data[:3]
    )
    ctx = t.get("_page_text", "")[:250].replace("\n", " ")

    prompt = f"""Classify this RBI Ombudsman Report table.

Context: {ctx}
Headers:
{hdr}

Choose ONE (reply JSON only, no explanation):
- fact_bank_category    rows=individual banks, cols=complaint categories (ATM/loans/cards)
- fact_bank_group       rows=bank groups (PSU/Private/Foreign totals), cols=years
- fact_bank_disposal    rows=banks, cols=maintainable/disposed/awards/implemented
- fact_region_complaints rows=OBO office names/cities, cols=complaint counts by year
- fact_category_totals  rows=complaint categories, cols=year+counts
- fact_disposal_modes   rows=disposal methods (settled/rejected/award), cols=year+counts
- fact_appeals          rows=OBOs, data about appeals against awards
- skip                  table of contents, chart index, cost data, irrelevant

{{"sub_type": "..."}}"""

    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "stream": False,
                  "options": {"temperature": 0.05, "num_predict": 60}},
            timeout=50,
        )
        text = r.json()["message"]["content"]
        j    = json.loads(text[text.find("{"):text.rfind("}") + 1])
        return j.get("sub_type", "skip")
    except Exception:
        return "skip"


# ─── Per-sub-type extractors ──────────────────────────────────────────────────

def extract_bank_category(t: dict, year_hint: str) -> dict:
    """
    Big appendix table: rows = individual banks, cols = complaint categories.
    Returns {"banks_found": [...], "records": [...]}
    """
    data  = t["data"]
    n_hdr = detect_n_header_rows(data)
    hdrs  = merge_header_rows(data[:n_hdr], n_hdr)

    # Locate name column and category columns
    skip_patterns = {
        "s.no", "serial", "total", "per branch", "per 1,000", "digital complaint",
        "non-digital", "annualized", "out of purview",
    }
    name_col = next(
        (i for i, h in enumerate(hdrs)
         if "name" in h.lower() and "bank" in h.lower()), 1
    )
    total_col = next(
        (i for i, h in enumerate(hdrs)
         if "total" in h.lower() and "received" in h.lower()), None
    )
    cat_cols: dict[int, str] = {}
    for i, h in enumerate(hdrs):
        hl = h.lower()
        if any(s in hl for s in skip_patterns):
            continue
        canon = canonicalise_category(h)
        if canon != h.strip() or any(k in hl for k in CATEGORY_CANONICAL):
            cat_cols[i] = canon

    banks_found: list[dict] = []
    records: list[dict]     = []
    current_type = "Unknown"

    for row in data[n_hdr:]:
        if not any(str(c).strip() for c in row):
            continue
        rt = row_text(row)

        # Group header row: "Public Sector Banks", "Foreign Banks", etc.
        is_group_header = False
        for kw, btype in BANK_TYPE_HEADERS.items():
            if kw in rt and sum(1 for c in row if str(c).strip()) <= 4:
                current_type = btype
                is_group_header = True
                break
        if is_group_header:
            continue

        # Skip percentage rows
        if is_percentage_row(row):
            continue

        bank_name = str(row[name_col]).strip().replace("\n", " ") if name_col < len(row) else ""
        if not bank_name or bank_name.isdigit() or len(bank_name) < 3:
            continue

        banks_found.append({"name": bank_name, "bank_type": current_type})

        # Total complaints for this bank
        if total_col is not None and total_col < len(row):
            tv = clean_num(row[total_col])
            if tv and 0 < tv < 2_000_000:
                records.append({
                    "bank_name": bank_name, "bank_type": current_type,
                    "category":  "TOTAL", "year": year_hint, "received": int(tv),
                })

        # Category-level counts
        for ci, cat in cat_cols.items():
            if ci < len(row):
                v = clean_num(row[ci])
                if v and 0 < v < 2_000_000:
                    records.append({
                        "bank_name": bank_name, "bank_type": current_type,
                        "category":  cat, "year": year_hint, "received": int(v),
                    })

    return {"banks_found": banks_found, "records": records}


def extract_bank_group(t: dict) -> list[dict]:
    """Bank group rollup: PSU / Private / Foreign × year."""
    data  = t["data"]
    n_hdr = detect_n_header_rows(data)
    hdrs  = merge_header_rows(data[:n_hdr], n_hdr)
    cy    = col_year_map(hdrs)
    records = []
    for row in data[n_hdr:]:
        rt = row_text(row)
        if is_percentage_row(row):
            continue
        bt = next((btype for kw, btype in BANK_TYPE_HEADERS.items() if kw in rt), None)
        if not bt:
            continue
        for ci, year in cy.items():
            if ci < len(row):
                v = clean_num(row[ci])
                if v and 0 < v < 5_000_000:
                    records.append({"bank_type": bt, "year": year, "received": int(v)})
    return records


def extract_bank_disposal(t: dict, year_hint: str) -> list[dict]:
    """Per-bank disposal: maintainable, disposed, awards_issued, awards_unimplemented."""
    data  = t["data"]
    n_hdr = detect_n_header_rows(data)
    hdrs  = merge_header_rows(data[:n_hdr], n_hdr)
    cy    = col_year_map(hdrs)

    # Locate key columns
    def find_col(keywords):
        return next((i for i, h in enumerate(hdrs)
                     if any(k in h.lower() for k in keywords)), None)

    name_col     = find_col(["name", "bank"])        or 0
    maint_col    = find_col(["maintainable"])
    disposed_col = find_col(["dispos"])
    award_col    = find_col(["award issued", "awards issued"])
    unimpl_col   = find_col(["unimplemented", "not implemented"])

    year = next(iter(cy.values()), year_hint)
    records = []
    current_type = "Unknown"

    for row in data[n_hdr:]:
        rt = row_text(row)
        if is_percentage_row(row):
            continue
        for kw, btype in BANK_TYPE_HEADERS.items():
            if kw in rt and sum(1 for c in row if str(c).strip()) <= 4:
                current_type = btype
                break
        else:
            name = str(row[name_col]).strip().replace("\n", " ") if name_col < len(row) else ""
            if not name or name.isdigit() or len(name) < 3:
                continue

            def _get(col):
                return int(v) if col is not None and col < len(row) and (v := clean_num(row[col])) and v > 0 else None

            records.append({
                "bank_name":           name,
                "bank_type":           current_type,
                "year":                year,
                "maintainable":        _get(maint_col),
                "disposed":            _get(disposed_col),
                "awards_issued":       _get(award_col),
                "awards_unimplemented": _get(unimpl_col),
            })
    return records


def extract_region_complaints(t: dict) -> list[dict]:
    """Per-OBO office complaint counts by year."""
    data  = t["data"]
    n_hdr = detect_n_header_rows(data)
    hdrs  = merge_header_rows(data[:n_hdr], n_hdr)
    cy    = col_year_map(hdrs)

    name_col = next(
        (i for i, h in enumerate(hdrs)
         if any(k in h.lower() for k in ["name", "obo", "odto", "nbfco", "oodt", "office"])),
        0
    )
    records = []
    for row in data[n_hdr:]:
        if not any(str(c).strip() for c in row):
            continue
        if is_percentage_row(row):
            continue
        office = str(row[name_col]).strip().replace("\n", " ") if name_col < len(row) else ""
        if not office or office.isdigit() or len(office) < 3:
            continue
        zone = infer_zone(office)
        for ci, year in cy.items():
            if ci == name_col or ci >= len(row):
                continue
            v = clean_num(row[ci])
            if v and 0 < v < 2_000_000:
                records.append({"office_name": office, "zone": zone, "year": year, "received": int(v)})
    return records


def extract_category_totals(t: dict) -> list[dict]:
    """Aggregate complaint counts by category and year."""
    data  = t["data"]
    n_hdr = detect_n_header_rows(data)
    hdrs  = merge_header_rows(data[:n_hdr], n_hdr)
    cy    = col_year_map(hdrs)
    records = []
    for row in data[n_hdr:]:
        if not any(str(c).strip() for c in row):
            continue
        if is_percentage_row(row):
            continue
        cat_raw = str(row[0]).strip().replace("\n", " ")
        if not cat_raw or cat_raw.isdigit() or len(cat_raw) < 3:
            continue
        canon = canonicalise_category(cat_raw)
        for ci, year in cy.items():
            if ci == 0 or ci >= len(row):
                continue
            v = clean_num(row[ci])
            if v and 0 < v < 5_000_000:
                records.append({"category": canon, "year": year, "received": int(v)})
    return records


def extract_disposal_modes(t: dict) -> list[dict]:
    """Disposal breakdown: mutual settlement / rejected / award / closed."""
    data  = t["data"]
    n_hdr = detect_n_header_rows(data)
    hdrs  = merge_header_rows(data[:n_hdr], n_hdr)
    cy    = col_year_map(hdrs)
    records = []
    for row in data[n_hdr:]:
        if not any(str(c).strip() for c in row):
            continue
        if is_percentage_row(row):
            continue
        mode = str(row[0]).strip().replace("\n", " ")
        if not mode or mode.isdigit() or len(mode) < 3:
            continue
        for ci, year in cy.items():
            if ci == 0 or ci >= len(row):
                continue
            v = clean_num(row[ci])
            if v and 0 < v < 2_000_000:
                records.append({"disposal_mode": mode, "year": year, "count": int(v)})
    return records


# ─── Schema assembler ─────────────────────────────────────────────────────────

def build_schema(buckets: dict) -> dict:
    """
    Assemble dimension + fact tables from raw extracted buckets.
    Returns {"banks", "regions", "complaint_categories", "complaints_annual"}
    """

    # ── Dimension: banks ─────────────────────────────────────────────────
    bank_lookup: dict[str, dict] = {}   # name_lower → {name, bank_type}
    for res in buckets.get("bank_category", []):
        for b in res.get("banks_found", []):
            k = b["name"].strip().lower()
            if k and k not in bank_lookup:
                bank_lookup[k] = {"name": b["name"].strip(), "bank_type": b.get("bank_type", "Unknown")}
    for recs in buckets.get("bank_disposal", []):
        for r in recs:
            k = r.get("bank_name", "").lower()
            if k and k not in bank_lookup:
                bank_lookup[k] = {"name": r["bank_name"], "bank_type": r.get("bank_type", "Unknown")}

    banks = [{"bank_id": i + 1, **v} for i, (_, v) in enumerate(bank_lookup.items())]
    bank_id_map = {b["name"].lower(): b["bank_id"] for b in banks}

    # ── Dimension: regions ───────────────────────────────────────────────
    region_lookup: dict[str, dict] = {}
    for r in buckets.get("region_complaints", []):
        k = r.get("office_name", "").lower()
        if k and k not in region_lookup:
            region_lookup[k] = {"office_name": r["office_name"], "zone": r.get("zone", "Unknown")}

    regions = [{"region_id": i + 1, **v} for i, (_, v) in enumerate(region_lookup.items())]
    region_id_map = {r["office_name"].lower(): r["region_id"] for r in regions}

    # ── Dimension: complaint_categories ──────────────────────────────────
    cat_lookup: dict[str, str] = {}
    for res in buckets.get("bank_category", []):
        for rec in res.get("records", []):
            cat = rec.get("category", "")
            if cat and cat != "TOTAL":
                cat_lookup[cat.lower()] = cat
    for rec in buckets.get("category_totals", []):
        cat = rec.get("category", "")
        if cat:
            cat_lookup[cat.lower()] = cat

    digital_kw = {"atm", "mobile", "internet", "electronic", "credit card", "debit"}
    categories = [
        {
            "category_id":    i + 1,
            "name":           v,
            "category_group": "Digital" if any(k in v.lower() for k in digital_kw) else "Non-Digital",
        }
        for i, (_, v) in enumerate(cat_lookup.items())
    ]
    cat_id_map = {c["name"].lower(): c["category_id"] for c in categories}

    # ── Fact: complaints_annual ───────────────────────────────────────────
    complaints: list[dict] = []
    cid = 1

    def _append(record):
        nonlocal cid
        complaints.append({"id": cid, **record})
        cid += 1

    # From bank × category
    for res in buckets.get("bank_category", []):
        for rec in res.get("records", []):
            if rec.get("category") == "TOTAL":
                continue
            _append({
                "bank_id":       bank_id_map.get(rec["bank_name"].lower()),
                "region_id":     None,
                "category_id":   cat_id_map.get(rec["category"].lower()),
                "year":          rec.get("year"),
                "received":      rec.get("received"),
                "disposed":      None,
                "awards_issued": None,
                "source_doc":    rec.get("_source"),
                "sub_type":      "fact_bank_category",
            })

    # From bank group
    for rec in buckets.get("bank_group", []):
        _append({
            "bank_id":       None,
            "region_id":     None,
            "category_id":   None,
            "year":          rec.get("year"),
            "received":      rec.get("received"),
            "disposed":      None,
            "awards_issued": None,
            "source_doc":    rec.get("_source"),
            "sub_type":      "fact_bank_group",
            "bank_type":     rec.get("bank_type"),  # extra field for rollup queries
        })

    # From region complaints
    for rec in buckets.get("region_complaints", []):
        _append({
            "bank_id":       None,
            "region_id":     region_id_map.get(rec["office_name"].lower()),
            "category_id":   None,
            "year":          rec.get("year"),
            "received":      rec.get("received"),
            "disposed":      None,
            "awards_issued": None,
            "source_doc":    rec.get("_source"),
            "sub_type":      "fact_region_complaints",
        })

    # From category totals
    for rec in buckets.get("category_totals", []):
        _append({
            "bank_id":       None,
            "region_id":     None,
            "category_id":   cat_id_map.get(rec["category"].lower()),
            "year":          rec.get("year"),
            "received":      rec.get("received"),
            "disposed":      None,
            "awards_issued": None,
            "source_doc":    rec.get("_source"),
            "sub_type":      "fact_category_totals",
        })

    # From disposal modes
    for rec in buckets.get("disposal_modes", []):
        _append({
            "bank_id":       None,
            "region_id":     None,
            "category_id":   None,
            "year":          rec.get("year"),
            "received":      None,
            "disposed":      rec.get("count"),
            "awards_issued": None,
            "disposal_mode": rec.get("disposal_mode"),
            "source_doc":    rec.get("_source"),
            "sub_type":      "fact_disposal_modes",
        })

    # From bank disposal
    for recs in buckets.get("bank_disposal", []):
        for rec in recs:
            _append({
                "bank_id":                bank_id_map.get((rec.get("bank_name") or "").lower()),
                "region_id":             None,
                "category_id":           None,
                "year":                  rec.get("year"),
                "received":              rec.get("maintainable"),
                "disposed":              rec.get("disposed"),
                "awards_issued":         rec.get("awards_issued"),
                "awards_unimplemented":  rec.get("awards_unimplemented"),
                "source_doc":            rec.get("_source"),
                "sub_type":              "fact_bank_disposal",
            })

    return {
        "banks":                banks,
        "regions":              regions,
        "complaint_categories": categories,
        "complaints_annual":    complaints,
    }


# ─── DDL ─────────────────────────────────────────────────────────────────────

DDL = """\
-- =============================================================================
-- RBI Ombudsman Complaints — Production Schema
-- Generated by schema_mapper.py
-- =============================================================================

CREATE TABLE banks (
    bank_id    SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    bank_type  TEXT NOT NULL DEFAULT 'Unknown'
               CHECK (bank_type IN (
                   'PSU','Private','Foreign','RRB',
                   'Cooperative','SFB','Payment Bank','NBFC','Unknown'))
);

CREATE TABLE regions (
    region_id   SERIAL PRIMARY KEY,
    office_name TEXT NOT NULL UNIQUE,
    zone        TEXT NOT NULL DEFAULT 'Unknown'
               CHECK (zone IN ('North','South','East','West','Central','Unknown'))
);

CREATE TABLE complaint_categories (
    category_id    SERIAL PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    category_group TEXT NOT NULL DEFAULT 'Non-Digital'
               CHECK (category_group IN ('Digital','Non-Digital','Other'))
);

CREATE TABLE complaints_annual (
    id                     SERIAL PRIMARY KEY,
    bank_id                INT REFERENCES banks(bank_id),
    region_id              INT REFERENCES regions(region_id),
    category_id            INT REFERENCES complaint_categories(category_id),
    year                   TEXT NOT NULL,           -- fiscal year e.g. '2020-21'
    received               INT,                     -- complaints received
    disposed               INT,                     -- complaints disposed/closed
    awards_issued          INT,
    awards_unimplemented   INT,
    award_amount_inr       NUMERIC,
    avg_resolution_days    NUMERIC,
    disposal_mode          TEXT,                    -- settled/rejected/award (disposal_modes rows)
    bank_type              TEXT,                    -- for bank_group rollup rows
    sub_type               TEXT,                    -- extraction sub-type
    source_doc             TEXT,                    -- "filename | page N"
    created_at             TIMESTAMP DEFAULT NOW()
);

-- Recommended indexes
CREATE INDEX ON complaints_annual (year);
CREATE INDEX ON complaints_annual (bank_id, year);
CREATE INDEX ON complaints_annual (region_id, year);
CREATE INDEX ON complaints_annual (category_id, year);
CREATE INDEX ON complaints_annual (sub_type);

-- =============================================================================
-- Quick-query views
-- =============================================================================

CREATE VIEW v_complaints_by_bank_year AS
SELECT b.name AS bank_name, b.bank_type, ca.year,
       SUM(ca.received) AS total_received,
       SUM(ca.disposed) AS total_disposed,
       SUM(ca.awards_issued) AS total_awards
FROM complaints_annual ca
JOIN banks b ON b.bank_id = ca.bank_id
WHERE ca.sub_type IN ('fact_bank_category','fact_bank_disposal')
GROUP BY b.name, b.bank_type, ca.year;

CREATE VIEW v_complaints_by_region_year AS
SELECT r.office_name, r.zone, ca.year,
       SUM(ca.received) AS total_received
FROM complaints_annual ca
JOIN regions r ON r.region_id = ca.region_id
WHERE ca.sub_type = 'fact_region_complaints'
GROUP BY r.office_name, r.zone, ca.year;

CREATE VIEW v_complaints_by_category_year AS
SELECT cc.name AS category, cc.category_group, ca.year,
       SUM(ca.received) AS total_received
FROM complaints_annual ca
JOIN complaint_categories cc ON cc.category_id = ca.category_id
WHERE ca.sub_type IN ('fact_bank_category','fact_category_totals')
GROUP BY cc.name, cc.category_group, ca.year;
"""

# ─── Load script ──────────────────────────────────────────────────────────────

LOAD_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"
load_to_db.py — Load schema JSON files into PostgreSQL.
Usage: python load_to_db.py --dsn 'postgresql://user:pass@host/db'
Requires: pip install psycopg2-binary
\"\"\"
import json, argparse, psycopg2, psycopg2.extras
from pathlib import Path

def load(dsn: str, schema_dir: str):
    conn = psycopg2.connect(dsn)
    cur  = conn.cursor()

    schema_path = Path(schema_dir)

    # Apply DDL
    cur.execute(open(schema_path / 'schema.sql').read())

    # Load dimensions first (FK order)
    for table in ['banks', 'regions', 'complaint_categories', 'complaints_annual']:
        data = json.loads((schema_path / f'{table}.json').read_text())
        if not data:
            continue
        cols   = list(data[0].keys())
        values = [[r.get(c) for c in cols] for r in data]
        sql    = f"INSERT INTO {table} ({','.join(cols)}) VALUES %s ON CONFLICT DO NOTHING"
        psycopg2.extras.execute_values(cur, sql, values)
        print(f"  Loaded {len(data):,} rows into {table}")

    conn.commit()
    cur.close()
    conn.close()
    print("Done.")

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dsn',    required=True)
    p.add_argument('--schema', default='schema')
    args = p.parse_args()
    load(args.dsn, args.schema)
"""


# ─── Main pipeline ────────────────────────────────────────────────────────────

def run(classified_path: str, output_dir: str, model: str, use_llm: bool) -> dict:
    print(f"📂  Loading {classified_path} …")
    with open(classified_path, encoding="utf-8") as f:
        tables = json.load(f)
    print(f"    {len(tables)} classified tables loaded\n")

    buckets: dict[str, list] = {
        "bank_category":    [],
        "bank_group":       [],
        "bank_disposal":    [],
        "region_complaints":[],
        "category_totals":  [],
        "disposal_modes":   [],
        "appeals":          [],
        "costs":            [],
    }
    sub_counts: dict[str, int] = {}

    for idx, t in enumerate(tables, 1):
        pct = idx / len(tables) * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"\r  [{bar}] {idx}/{len(tables)} ({pct:.0f}%)", end="", flush=True)

        sub = heuristic_subtype(t)
        if sub == "skip" and use_llm and t.get("rows", 0) >= 5 and t.get("cols", 0) >= 3:
            sub = llm_subtype(t, model)

        sub_counts[sub] = sub_counts.get(sub, 0) + 1
        src = f"{t.get('file','')} | page {t.get('page','?')}"

        # Extract year from filename
        yr_list = extract_year(t.get("file", ""))
        yr = yr_list[0] if yr_list else t.get("year", "unknown")

        def tag(recs):
            if isinstance(recs, list):
                for r in recs:
                    r["_source"] = src
            elif isinstance(recs, dict):
                for r in recs.get("records", []):
                    r["_source"] = src
            return recs

        if sub == "fact_bank_category":
            buckets["bank_category"].append(tag(extract_bank_category(t, yr)))
        elif sub == "fact_bank_group":
            buckets["bank_group"].extend(tag(extract_bank_group(t)))
        elif sub == "fact_bank_disposal":
            buckets["bank_disposal"].append(tag(extract_bank_disposal(t, yr)))
        elif sub == "fact_region_complaints":
            buckets["region_complaints"].extend(tag(extract_region_complaints(t)))
        elif sub == "fact_category_totals":
            buckets["category_totals"].extend(tag(extract_category_totals(t)))
        elif sub == "fact_disposal_modes":
            buckets["disposal_modes"].extend(tag(extract_disposal_modes(t)))

    print()

    # ── Assemble schema ───────────────────────────────────────────────────
    print("\n🔧  Assembling schema tables …")
    schema = build_schema(buckets)

    # ── Save outputs ──────────────────────────────────────────────────────
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for table_name, records in schema.items():
        p = out / f"{table_name}.json"
        p.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"     {table_name:28s} → {p}  ({len(records):,} records)")

    (out / "schema.sql").write_text(DDL, encoding="utf-8")
    print(f"     {'schema.sql':28s} → {out}/schema.sql")

    (out / "load_to_db.py").write_text(LOAD_SCRIPT, encoding="utf-8")
    print(f"     {'load_to_db.py':28s} → {out}/load_to_db.py")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n📊  Sub-type breakdown:")
    for s, n in sorted(sub_counts.items(), key=lambda x: -x[1]):
        print(f"     {s:32s}: {n:4d}")

    return schema


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Map Ombudsman classified tables → production schema JSON + SQL"
    )
    p.add_argument("--input",  default="output/classified_tables.json",
                   help="Path to classified_tables.json")
    p.add_argument("--output", default="schema",
                   help="Output directory (default: ./schema)")
    p.add_argument("--model",  default=DEFAULT_MODEL,
                   help=f"Ollama model (default: {DEFAULT_MODEL})")
    p.add_argument("--no-llm", action="store_true",
                   help="Skip Qwen fallback — heuristics only (faster)")
    args = p.parse_args()

    run(
        classified_path=args.input,
        output_dir=args.output,
        model=args.model,
        use_llm=not args.no_llm,
    )


if __name__ == "__main__":
    main()
