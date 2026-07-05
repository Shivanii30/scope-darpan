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
