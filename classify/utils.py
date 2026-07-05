"""
utils.py
────────
General helper functions: table quality checks, keyword matching,
table formatting/cleaning, and misc small utilities.
"""

import re

from config import (
    CATEGORY_KEYWORDS,
    MAX_TABLE_ROWS,
    MIN_COLS,
    MIN_NONEMPTY,
    MIN_ROWS,
)


def is_quality_table(table: dict) -> bool:
    """Return True if the table has enough substance to be worth classifying."""
    data = table.get("data", [])
    non_empty = sum(1 for row in data for cell in row if str(cell).strip())
    return (
        table.get("rows", 0) >= MIN_ROWS
        and table.get("cols", 0) >= MIN_COLS
        and non_empty >= MIN_NONEMPTY
    )


def keyword_candidates(page_text: str, table: dict) -> list[str]:
    """Return matching category names based on keyword scan."""
    first_rows_text = " ".join(
        " ".join(str(c) for c in row)
        for row in table.get("data", [])[:3]
    )
    search_text = (page_text[:500] + " " + first_rows_text).lower()

    matched = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in search_text for kw in kws):
            matched.append(cat)
    return matched


def format_table_for_llm(data: list[list], max_rows: int = MAX_TABLE_ROWS) -> str:
    """Compact pipe-separated table string, truncated for token budget."""
    lines = []
    for row in data[:max_rows]:
        cells = [str(c).strip()[:28] for c in row]
        non_empty = [c for c in cells if c]
        if non_empty:
            lines.append(" | ".join(cells))
    return "\n".join(lines) if lines else "(empty)"


def clean_table_data(data: list[list]) -> list[list]:
    """Strip whitespace, replace None with empty string."""
    return [
        [str(cell).strip() if cell is not None else "" for cell in row]
        for row in data
    ]


def extract_year(filename: str) -> str:
    """Pull the fiscal year string from the filename."""
    m = re.search(r"(\d{4}[-–]\d{2,4})", filename)
    return m.group(1) if m else "unknown"
