"""Container-friendly, drift-gated DARPAN batch pipeline (M0-M7)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from acceptance import run_checks
from config import DARPAN_ROOT, OUTPUT_DIR, drift_policy, send_alert
from drift import accept_baseline, compare, current_snapshot, get_baseline_before_m0, should_block, write_report


STAGES = [
    ("m0", [sys.executable, str(DARPAN_ROOT / "m4" / "pipeline.py"), "--stage", "m0"]),
    ("m1", [sys.executable, str(DARPAN_ROOT / "m4" / "pipeline.py"), "--stage", "m1"]),
    ("m2", [sys.executable, str(DARPAN_ROOT / "m4" / "pipeline.py"), "--stage", "m2"]),
    ("m3", [sys.executable, str(DARPAN_ROOT / "m4" / "pipeline.py"), "--stage", "m3"]),
    ("m5", [sys.executable, str(DARPAN_ROOT / "m5" / "run.py")]),
    ("m6", [sys.executable, str(DARPAN_ROOT / "m6" / "run.py")]),
    ("m7", [sys.executable, str(DARPAN_ROOT / "m7" / "run.py")]),
]


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args():
    parser = argparse.ArgumentParser(description="Run and validate the DARPAN M0-M7 pipeline")
    parser.add_argument("--accept-drift", action="store_true",
                        help="Proceed after reviewing detected source/schema drift; baseline is updated only if all gates pass")
    return parser.parse_args()


def run_stage(stage: str, command: list[str], run_dir: Path) -> dict:
    started = time.monotonic()
    print(f"=== {stage.upper()} ===", flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=DARPAN_ROOT / ("m4" if stage in {"m0", "m1", "m2", "m3"} else stage),
            capture_output=True,
            text=True,
            check=False,
            timeout=7200,
        )
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stderr += "\nM10 timeout: stage exceeded 7200 seconds\n"
        exit_code = 124

    (run_dir / f"{stage}.stdout.log").write_text(stdout, encoding="utf-8")
    (run_dir / f"{stage}.stderr.log").write_text(stderr, encoding="utf-8")
    print(stdout, end="", flush=True)
    if stderr:
        print(stderr, file=sys.stderr, end="", flush=True)
    return {
        "stage": stage,
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 2),
        "stdout_log": str(run_dir / f"{stage}.stdout.log"),
        "stderr_log": str(run_dir / f"{stage}.stderr.log"),
    }


def stage_gate(stage: str) -> tuple[bool, str]:
    paths = {
        "m0": (DARPAN_ROOT / "m0" / "outputs" / "extraction_strategy_map.csv", None),
        "m1": (DARPAN_ROOT / "m1" / "outputs" / "extraction_summary.json", "spot_checks"),
        "m2": (DARPAN_ROOT / "m2" / "outputs" / "validation.json", "ok"),
        "m3": (DARPAN_ROOT / "m3" / "outputs" / "m3_summary.json", "validation"),
        "m5": (DARPAN_ROOT / "m5" / "outputs" / "m5_summary.json", "validation"),
        "m6": (DARPAN_ROOT / "m6" / "outputs" / "m6_summary.json", "validation"),
        "m7": (DARPAN_ROOT / "m7" / "outputs" / "m7_summary.json", "validation"),
    }
    path, key = paths[stage]
    if not path.exists():
        return False, f"required artifact missing: {path}"
    if stage == "m0":
        return True, "strategy map exists"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if stage == "m1":
            passed = data.get("spot_checks", {}).get("failed") == 0
            return passed, "M1 spot checks passed" if passed else "M1 spot checks failed"
        if stage == "m2":
            passed = data.get("ok") is True
        else:
            passed = data.get(key, {}).get("ok") is True
        return passed, "validation passed" if passed else "validation gate failed"
    except Exception as exc:
        return False, f"cannot read validation artifact: {exc}"


def write_latest(summary: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    started = timestamp()
    run_dir = OUTPUT_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    policy = drift_policy()
    old_snapshot = get_baseline_before_m0()
    stage_results: list[dict] = []
    started_clock = time.monotonic()
    final_status = "failed"
    drift_changes: list[dict] = []
    new_snapshot: dict | None = None
    acceptance: dict = {"ok": False, "checks": []}

    for stage, command in STAGES:
        result = run_stage(stage, command, run_dir)
        passed, detail = (result["exit_code"] == 0, f"exit_code={result['exit_code']}")
        if passed:
            passed, detail = stage_gate(stage)
        result["gate"] = {"ok": passed, "detail": detail}
        stage_results.append(result)

        if not passed:
            break

        if stage == "m0":
            new_snapshot = current_snapshot()
            drift_changes = compare(old_snapshot, new_snapshot)
            drift_report_path = write_report(old_snapshot, new_snapshot, drift_changes, policy, args.accept_drift)
            result["drift_report"] = str(drift_report_path)
            result["drift_count"] = len(drift_changes)
            critical_count = sum(change["severity"] == "critical" for change in drift_changes)
            if drift_changes:
                send_alert("DARPAN source/schema drift detected",
                           f"run_id={run_id}; changes={len(drift_changes)}; critical={critical_count}; policy={policy}",
                           status="drift_detected")
                if should_block(drift_changes, policy, args.accept_drift):
                    result["gate"] = {"ok": False, "detail": "drift policy blocks downstream stages; review drift_report.json and rerun with --accept-drift"}
                    break

    stages_passed = len(stage_results) == len(STAGES) and all(item["gate"]["ok"] for item in stage_results)
    if stages_passed:
        api_url = os.getenv("DARPAN_API_URL", "").strip()
        acceptance = run_checks(api_url or None)
        (OUTPUT_DIR / "acceptance.json").write_text(json.dumps(acceptance, indent=2), encoding="utf-8")
        final_status = "passed" if acceptance["ok"] else "acceptance_failed"
        if final_status == "passed" and new_snapshot is not None:
            accept_baseline(new_snapshot)
    elif stage_results and stage_results[-1].get("drift_count", 0) > 0 and not args.accept_drift and policy == "block":
        final_status = "drift_blocked"

    duration = round(time.monotonic() - started_clock, 2)
    def artifact_count(path: Path, key: str):
        try:
            return json.loads(path.read_text(encoding="utf-8")).get(key)
        except Exception:
            return None

    def nested_count(path: Path, parent: str, key: str):
        try:
            return json.loads(path.read_text(encoding="utf-8")).get(parent, {}).get(key)
        except Exception:
            return None

    summary = {
        "run_id": run_id,
        "started_at": started,
        "finished_at": timestamp(),
        "duration_seconds": duration,
        "status": final_status,
        "drift_policy": policy,
        "drift_changes": len(drift_changes),
        "drift_accepted_by_operator": args.accept_drift,
        "acceptance": acceptance,
        "metrics": {
            "source_pdfs": (new_snapshot or {}).get("source_count"),
            "tables_extracted": artifact_count(DARPAN_ROOT / "m1" / "outputs" / "extraction_summary.json", "total_tables_extracted"),
            "normalized_facts": artifact_count(DARPAN_ROOT / "m2" / "outputs" / "run_summary.json", "normalized_facts"),
            "anomalies": nested_count(DARPAN_ROOT / "m6" / "outputs" / "m6_summary.json", "validation", "anomalies"),
            "briefs": nested_count(DARPAN_ROOT / "m7" / "outputs" / "m7_summary.json", "validation", "briefs"),
            "drift_items": len(drift_changes),
        },
        "stages": stage_results,
        "run_dir": str(run_dir),
    }
    write_latest(summary)
    if final_status != "passed":
        send_alert("DARPAN pipeline run failed", f"run_id={run_id}; status={final_status}; duration_seconds={duration}", status=final_status)
        print(f"Pipeline {final_status}. Details: {OUTPUT_DIR / 'latest.json'}", file=sys.stderr, flush=True)
        return 1

    print(f"Full pipeline passed in {duration:.1f}s. Logs: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
