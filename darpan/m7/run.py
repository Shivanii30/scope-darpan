"""M7 runner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generator import generate_brief, read_csv, M5_CSV, M6_CSV, OUTPUT_DIR


def validate(briefs: list[dict]) -> dict:
    errors: list[str] = []
    required_sections = (
        "executive_summary", "trend_analysis", "stress_score_rationale",
        "peer_positioning", "anomalies_flagged", "data_provenance",
    )
    for brief in briefs:
        for section in required_sections:
            if section not in brief:
                errors.append(f"{brief.get('bank_id')} missing {section}")
        if not brief.get("markdown"):
            errors.append(f"{brief.get('bank_id')} missing markdown")
    return {"ok": not errors, "errors": errors, "briefs": len(briefs)}


def main() -> int:
    print("=" * 64)
    print("M7 — Policy brief generator")
    print("=" * 64)

    missing = [p for p in (M5_CSV, M6_CSV) if not p.exists()]
    if missing:
        print("ERROR: M5/M6 output missing", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scores = read_csv(M5_CSV)
    anomalies = read_csv(M6_CSV)

    briefs = [generate_brief(row, scores, anomalies) for row in scores]
    validation = validate(briefs)

    (OUTPUT_DIR / "briefs.json").write_text(json.dumps(briefs, indent=2), encoding="utf-8")

    for brief in briefs:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in brief["bank_id"])
        (OUTPUT_DIR / f"{safe_name}.md").write_text(brief["markdown"], encoding="utf-8")

    summary = {
        "m5_source": str(M5_CSV),
        "m6_source": str(M6_CSV),
        "validation": validation,
    }
    (OUTPUT_DIR / "m7_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"  Policy briefs: {len(briefs)}")
    print(f"  Validation: {'PASS' if validation['ok'] else 'FAIL'}")
    print("=" * 64)
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
