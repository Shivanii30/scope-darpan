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
