"""
M0 — run all stages in one command.

  python -m darpan.m0.run

Steps:
  1. audit_pdfs.py  — scan all PDFs, write source_inventory.{json,csv}
  2. classify.py    — assign era + extraction strategy, write drift log

After this finishes, downstream modules (M1, M2) read:
  - outputs/source_inventory.json
  - outputs/extraction_strategy_map.csv
  - outputs/format_drift_log.md
"""
from __future__ import annotations

import sys
from pathlib import Path

# allow `python run.py` from inside the m0 dir
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_pdfs as audit  # noqa: E402
import classify  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("M0 — Data reconnaissance & schema design")
    print("=" * 60)
    print()

    print("Step 1/2 — audit_pdfs.py: scanning source PDFs")
    print("-" * 60)
    rc = audit.main()
    if rc != 0:
        return rc
    print()

    print("Step 2/2 — classify.py: era + strategy assignment")
    print("-" * 60)
    rc = classify.main()
    if rc != 0:
        return rc

    print()
    print("=" * 60)
    print("M0 complete.  Next: M1 (PDF extraction engine).")
    print("  read:  darpan/m0/outputs/format_drift_log.md")
    print("  use:   darpan/m0/outputs/extraction_strategy_map.csv")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
