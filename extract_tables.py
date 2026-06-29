import json
import re
from pathlib import Path

import camelot
import pandas as pd
import pdfplumber

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

RAW_DIR = Path("data/raw/")
OUTPUT_DIR = Path("data/extracted")
TABLE_MAP = Path("table_map.json")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# LOAD TABLE MAP
# --------------------------------------------------

with open(TABLE_MAP, "r", encoding="utf-8") as f:
    table_map = json.load(f)

print("Loaded table map for years:", list(table_map.keys()))

# --------------------------------------------------
# GET YEAR FROM FILENAME
# --------------------------------------------------

def extract_year(filename):
    m = re.search(r"(\d{4}-\d{2})", filename)
    return m.group(1) if m else None

print("Extracting tables from PDFs in:", RAW_DIR)

# --------------------------------------------------
# READ TOC
# --------------------------------------------------

def extract_toc(pdf_path, max_pages=12):
    """
    Returns

    {
        "Table 1.1": 2,
        "Table 1.2": 5,
        ...
    }

    where value = printed page number
    """

    toc = {}

    pattern = re.compile(
        r"(Table\s+\d+(?:\.\d+)?)\s+.*?(\d+)\s*$",
        re.IGNORECASE
    )

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages[:max_pages]:

            text = page.extract_text()

            if not text:
                continue

            for line in text.split("\n"):

                m = pattern.search(line)

                if m:
                    table_id = m.group(1).strip()
                    printed_page = int(m.group(2))

                    toc[table_id] = printed_page

    return toc

print("Extracting TOC from PDFs in:", RAW_DIR)

# --------------------------------------------------
# FIND PAGE OFFSET
# --------------------------------------------------

def detect_page_offset(pdf_path):
    """
    Finds first printed page and computes

    pdf_page = printed_page + offset
    """

    footer_pattern = re.compile(r"^\s*(\d+)\s*$")

    with pdfplumber.open(pdf_path) as pdf:

        for pdf_index, page in enumerate(pdf.pages, start=1):

            text = page.extract_text()

            if not text:
                continue

            lines = text.split("\n")

            if not lines:
                continue

            footer = lines[-1].strip()

            m = footer_pattern.match(footer)

            if m:

                printed = int(m.group(1))

                return pdf_index - printed

    raise RuntimeError("Could not detect page offset.")

print("Detecting page offsets for PDFs in:", RAW_DIR)

# --------------------------------------------------
# EXTRACT TABLE
# --------------------------------------------------

def extract_table(pdf_path, pdf_page):

    tables = camelot.read_pdf(
        str(pdf_path),
        pages=str(pdf_page),
        flavor="lattice"
    )

    if len(tables) == 0:

        tables = camelot.read_pdf(
            str(pdf_path),
            pages=str(pdf_page),
            flavor="stream"
        )

    return tables
print("Extracting tables from PDFs in:", RAW_DIR)
# --------------------------------------------------
# MAIN
# --------------------------------------------------

for pdf in RAW_DIR.glob("*.pdf"):

    year = extract_year(pdf.name)

    if year not in table_map:
        print(f"Skipping {pdf.name}")
        continue

    print("=" * 70)
    print(pdf.name)

    toc = extract_toc(pdf)

    offset = detect_page_offset(pdf)

    print("Offset:", offset)

    year_out = OUTPUT_DIR / year
    year_out.mkdir(exist_ok=True)

    for category, table_ids in table_map[year].items():

        cat_out = year_out / category
        cat_out.mkdir(exist_ok=True)

        for table_id in table_ids:

            if table_id not in toc:

                print(f"Missing {table_id}")

                continue

            printed_page = toc[table_id]

            pdf_page = printed_page + offset

            print(
                f"{table_id} "
                f"printed={printed_page} "
                f"pdf={pdf_page}"
            )

            tables = extract_table(pdf, pdf_page)

            if len(tables) == 0:

                print("   No table detected.")

                continue

            for i, table in enumerate(tables):

                outfile = (
                    cat_out /
                    f"{table_id.replace(' ', '_').replace('.', '_')}_{i+1}.csv"
                )

                table.df.to_csv(outfile, index=False)

                print("   Saved:", outfile)

print("\nDone.")