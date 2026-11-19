"""Monthly/quarterly scheduler with heartbeat and overlap lock."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import OUTPUT_DIR, schedule_hour_utc, schedule_kind, send_alert


M10_ROOT = Path(__file__).resolve().parent
HEARTBEAT = OUTPUT_DIR / "scheduler_heartbeat.json"
LOCK = OUTPUT_DIR / "scheduler.lock"


def next_run(now: datetime, cadence: str, hour: int) -> datetime:
    now = now.astimezone(timezone.utc)
    year, month = now.year, now.month
    if cadence == "quarterly":
        month = ((month - 1) // 3) * 3 + 1
    candidate = datetime(year, month, 1, hour, tzinfo=timezone.utc)
    if candidate <= now:
        month += 1 if cadence == "monthly" else 3
        while month > 12:
            year += 1
            month -= 12
        candidate = datetime(year, month, 1, hour, tzinfo=timezone.utc)
    return candidate


def write_heartbeat(status: str, *, scheduled_at: str | None = None, detail: str = "") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(json.dumps({
        "status": status,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schedule": schedule_kind(),
        "scheduled_at": scheduled_at,
        "detail": detail,
    }, indent=2), encoding="utf-8")


def run_job() -> int:
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            stale = time.time() - LOCK.stat().st_mtime > 3 * 60 * 60
        except FileNotFoundError:
            stale = True
        if stale:
            try:
                LOCK.unlink()
            except FileNotFoundError:
                pass
            try:
                fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                write_heartbeat("busy", detail="A pipeline run already holds the scheduler lock")
                return 2
        else:
            write_heartbeat("busy", detail="A pipeline run already holds the scheduler lock")
            return 2

    os.close(fd)
    try:
        write_heartbeat("running")
        result = subprocess.run(
            [sys.executable, str(M10_ROOT / "run_pipeline.py")],
            cwd=M10_ROOT.parents[1],
            check=False,
        )
        status = "passed" if result.returncode == 0 else "failed"
        write_heartbeat(status, detail=f"pipeline_exit_code={result.returncode}")
        if result.returncode:
            send_alert("DARPAN scheduled pipeline failed", f"exit_code={result.returncode}", status="failed")
        return result.returncode
    finally:
        try:
            LOCK.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cadence = schedule_kind()
    hour = schedule_hour_utc()
    write_heartbeat("waiting")
    run_on_start = os.getenv("DARPAN_RUN_ON_START", "false").strip().lower() in {"1", "true", "yes"}
    if run_on_start:
        run_job()

    while True:
        now = datetime.now(timezone.utc)
        due = next_run(now, cadence, hour)
        write_heartbeat("waiting", scheduled_at=due.isoformat(timespec="seconds"))
        while datetime.now(timezone.utc) < due:
            time.sleep(min(60, max(1, (due - datetime.now(timezone.utc)).total_seconds())))
            write_heartbeat("waiting", scheduled_at=due.isoformat(timespec="seconds"))
        run_job()
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
