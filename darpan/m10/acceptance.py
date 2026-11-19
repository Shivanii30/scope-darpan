"""Deployment and pipeline acceptance checks."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from .config import DARPAN_ROOT
except ImportError:
    from config import DARPAN_ROOT

EXPECTED_YEAR_COUNT = 9


def run_checks(api_url: str | None = None) -> dict:
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def read(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"_error": str(exc)}

    m1 = read(DARPAN_ROOT / "m1" / "outputs" / "extraction_summary.json")
    m1_ok = not m1.get("_error") and m1.get("spot_checks", {}).get("failed") == 0
    record("m1_validation", m1_ok, m1.get("_error", f"spot_checks={m1.get('spot_checks', {})}"))

    m2 = read(DARPAN_ROOT / "m2" / "outputs" / "validation.json")
    record("m2_validation", bool(m2.get("ok")), m2.get("_error", "; ".join(m2.get("errors", [])) or "validation passed"))

    m3 = read(DARPAN_ROOT / "m3" / "outputs" / "m3_summary.json")
    record("m3_database_validation", bool(m3.get("validation", {}).get("ok")), m3.get("_error", "M3 summary validation"))

    m3_db = DARPAN_ROOT / "m3" / "outputs" / "darpan.sqlite"
    try:
        con = sqlite3.connect(f"file:{m3_db}?mode=ro", uri=True)
        fact_count = con.execute("SELECT COUNT(*) FROM complaints_annual").fetchone()[0]
        year_count = con.execute("SELECT COUNT(DISTINCT year) FROM complaints_annual").fetchone()[0]
        con.close()
        record("m3_fact_coverage", fact_count > 0 and year_count == EXPECTED_YEAR_COUNT,
               f"facts={fact_count}; reporting_years={year_count}")
    except Exception as exc:
        record("m3_fact_coverage", False, str(exc))

    for module, summary_name in (("m5", "m5_summary.json"), ("m6", "m6_summary.json"), ("m7", "m7_summary.json")):
        summary = read(DARPAN_ROOT / module / "outputs" / summary_name)
        ok = summary.get("validation", {}).get("ok") is True
        record(f"{module}_validation", ok, summary.get("_error", "validation passed" if ok else "validation not passed"))

    if api_url:
        try:
            with urllib.request.urlopen(api_url.rstrip("/") + "/health", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            ok = response.status == 200 and payload.get("status") == "ok"
            record("api_health", ok, f"status={response.status}; banks={payload.get('m5_scores')}")
        except Exception as exc:
            record("api_health", False, str(exc))

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


if __name__ == "__main__":
    api_url = os.getenv("DARPAN_API_URL", "").strip() or None
    result = run_checks(api_url)
    output = DARPAN_ROOT / "m10" / "outputs" / "acceptance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
