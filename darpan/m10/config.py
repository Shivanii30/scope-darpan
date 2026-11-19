"""M10 environment configuration and secret-safe alerts."""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


DARPAN_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
STATE_DIR = Path(__file__).resolve().parent / "state"
SOURCE_DIR = DARPAN_ROOT.parent / "Ombudsman"


def drift_policy() -> str:
    value = os.getenv("DARPAN_DRIFT_POLICY", "block").strip().lower()
    if value not in {"block", "warn"}:
        raise ValueError("DARPAN_DRIFT_POLICY must be 'block' or 'warn'")
    return value


def schedule_kind() -> str:
    value = os.getenv("DARPAN_PIPELINE_SCHEDULE", "monthly").strip().lower()
    if value not in {"monthly", "quarterly"}:
        raise ValueError("DARPAN_PIPELINE_SCHEDULE must be 'monthly' or 'quarterly'")
    return value


def schedule_hour_utc() -> int:
    value = int(os.getenv("DARPAN_SCHEDULE_HOUR_UTC", "3"))
    if not 0 <= value <= 23:
        raise ValueError("DARPAN_SCHEDULE_HOUR_UTC must be from 0 to 23")
    return value


def send_alert(title: str, message: str, *, status: str) -> bool:
    """POST a secret-free alert payload if a webhook is configured.

    The webhook URL is never included in logs, metrics, or exceptions.
    """
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    secret_file = Path(os.getenv("ALERT_WEBHOOK_FILE", "/run/secrets/alert_webhook_url"))
    if not url and secret_file.is_file():
        url = secret_file.read_text(encoding="utf-8").strip()
    if not url:
        return False
    body = json.dumps({
        "application": "DARPAN",
        "title": title,
        "message": message,
        "status": status,
        "text": f"{title}: {message}",
        "content": f"{title}: {message}",
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except Exception:
        return False
