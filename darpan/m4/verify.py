from __future__ import annotations

import json
from pathlib import Path

latest = Path(__file__).resolve().parent / "outputs" / "latest.json"
if not latest.exists():
    raise SystemExit("M4 latest run manifest not found")

manifest = json.loads(latest.read_text(encoding="utf-8"))
print("status", manifest["status"])
print("stages", [(r["stage"], r["status"]) for r in manifest["stages"]])
raise SystemExit(0 if manifest["status"] == "passed" else 1)
