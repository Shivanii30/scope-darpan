"""Container healthcheck helpers for M10."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT = Path(__file__).resolve().parent / "outputs" / "scheduler_heartbeat.json"


def main() -> int:
    try:
        payload = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        beat = datetime.fromisoformat(payload["heartbeat_at"])
        age = (datetime.now(timezone.utc) - beat.astimezone(timezone.utc)).total_seconds()
        if age > 180:
            return 1
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
