"""
M1 — extraction router.

Reads M0's `extraction_strategy_map.csv` and dispatches each PDF to the
correct extraction backend. Today M0 says all 9 PDFs are `native`, so
this router wires them all to the pdfplumber-based native extractor.
The OCR branch is implemented as a `NotImplementedError` stub that
fails loudly — when M0 flags a PDF as `ocr` or `hybrid`, the operator
gets a clear "build the OCR adapter" message rather than a silent skip.

The router's job is intentionally small: M1's plan says "don't assume
one extractor works for all years" — that warning is enforced by making
the OCR branch fail loudly until an adapter is built.
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path


M0_OUTPUTS = Path(__file__).resolve().parents[1] / "m0" / "outputs"


@dataclass
class RouterDecision:
    filename: str
    reporting_year: str
    format_era: str
    schema_variant: str
    strategy: str           # native | hybrid | ocr
    pdf_path: Path


def load_strategy_map() -> list[RouterDecision]:
    """Parse M0's extraction_strategy_map.csv into a list of router decisions."""
    csv_path = M0_OUTPUTS / "extraction_strategy_map.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"M0 not run yet — missing {csv_path}. Run: python -m m0.run"
        )

    repo_root = Path(__file__).resolve().parents[2]
    pdf_dir = repo_root / "Ombudsman"

    decisions: list[RouterDecision] = []
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pdf_path = pdf_dir / row["filename"]
            if not pdf_path.exists():
                print(f"  WARN: PDF listed in strategy map but missing on disk: {pdf_path}",
                      file=sys.stderr)
                continue
            decisions.append(RouterDecision(
                filename=row["filename"],
                reporting_year=row["reporting_year"],
                format_era=row["format_era"],
                schema_variant=row["schema_variant"],
                strategy=row["extraction_strategy"],
                pdf_path=pdf_path,
            ))
    return decisions


def dispatch(decision: RouterDecision):
    """Return the right extraction function for this PDF. M0 has the
    final say on strategy; M1 just routes."""
    if decision.strategy == "native":
        from native_extractor import extract_native
        return extract_native
    if decision.strategy == "hybrid":
        # M0 plans for this; not built yet. Fail loud, not silent.
        raise NotImplementedError(
            f"Hybrid strategy requested for {decision.filename} but no hybrid "
            "adapter is implemented. Build one in hybrid_extractor.py and "
            "import it here."
        )
    if decision.strategy == "ocr":
        raise NotImplementedError(
            f"OCR strategy requested for {decision.filename} — Tesseract / "
            "LayoutLMv3 adapter is not implemented in M1 yet. The plan says "
            "to wire this in M1.2 after the native path is validated."
        )
    raise ValueError(f"Unknown strategy {decision.strategy!r} for {decision.filename}")
