"""M4 pipeline orchestration.

Runs M0 -> M1 -> M2 -> M3 with dependency-aware gates and rerun support.
Uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


PYTHON = sys.executable
ROOT = Path(__file__).resolve().parents[1]
DARPAN_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs"

STAGES = (
    "m0",
    "m1",
    "m2",
    "m3",
)


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stage_commands(stage: str) -> list[list[str]]:
    if stage == "m0":
        return [[PYTHON, str(DARPAN_ROOT / "m0" / "run.py")]]
    if stage == "m1":
        return [[PYTHON, str(DARPAN_ROOT / "m1" / "run.py")]]
    if stage == "m2":
        return [[PYTHON, str(DARPAN_ROOT / "m2" / "run.py")]]
    if stage == "m3":
        return [[PYTHON, str(DARPAN_ROOT / "m3" / "run.py")]]
    raise ValueError(f"Unknown stage: {stage}")


def preflight(stage: str) -> list[str]:
    errors: list[str] = []
    m0 = DARPAN_ROOT / "m0" / "outputs"
    m1 = DARPAN_ROOT / "m1" / "outputs"
    m2 = DARPAN_ROOT / "m2" / "outputs"

    if stage in ("m1", "m2", "m3"):
        map_path = m0 / "extraction_strategy_map.csv"
        if not map_path.exists():
            errors.append(f"missing M0 artifact: {map_path}")
    if stage in ("m2", "m3"):
        if not (m1 / "extracted").exists():
            errors.append(f"missing M1 artifact directory: {m1 / 'extracted'}")
    if stage == "m3":
        for path in (
            m2 / "normalized_complaints.csv",
            m2 / "staging" / "staging_tables.csv",
            m2 / "rejections.csv",
        ):
            if not path.exists():
                errors.append(f"missing M2 artifact: {path}")
    return errors


def artifact_gate(stage: str) -> list[str]:
    errors: list[str] = []
    m0 = DARPAN_ROOT / "m0" / "outputs"
    m1 = DARPAN_ROOT / "m1" / "outputs"
    m2 = DARPAN_ROOT / "m2" / "outputs"
    m3 = DARPAN_ROOT / "m3" / "outputs"

    if stage == "m0":
        for path in (m0 / "source_inventory.json", m0 / "format_drift_log.json", m0 / "extraction_strategy_map.csv"):
            if not path.exists():
                errors.append(f"missing post-run M0 artifact: {path}")

    if stage == "m1":
        summary_path = m1 / "extraction_summary.json"
        if not summary_path.exists():
            errors.append(f"missing post-run M1 artifact: {summary_path}")
        else:
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if summary.get("spot_checks", {}).get("failed", 1) != 0:
                    errors.append("M1 spot-check gate failed")
            except Exception as exc:
                errors.append(f"cannot read M1 summary: {exc}")

    if stage == "m2":
        validation_path = m2 / "validation.json"
        if not validation_path.exists():
            errors.append(f"missing post-run M2 artifact: {validation_path}")
        else:
            try:
                validation = json.loads(validation_path.read_text(encoding="utf-8"))
                if not validation.get("ok"):
                    errors.append("M2 validation gate failed: " + "; ".join(validation.get("errors", [])))
            except Exception as exc:
                errors.append(f"cannot read M2 validation: {exc}")

    if stage == "m3":
        summary_path = m3 / "m3_summary.json"
        if not summary_path.exists():
            errors.append(f"missing post-run M3 artifact: {summary_path}")
        else:
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if not summary.get("validation", {}).get("ok"):
                    errors.append("M3 database validation gate failed")
            except Exception as exc:
                errors.append(f"cannot read M3 summary: {exc}")

    return errors


def run_command(command: list[str], cwd: Path, run_dir: Path, stage: str) -> dict:
    stdout_path = run_dir / f"{stage}.stdout.log"
    stderr_path = run_dir / f"{stage}.stderr.log"

    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3600,
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        return {
            "stage": stage,
            "command": command,
            "cwd": str(cwd),
            "started_at": utc_now(),
            "exit_code": completed.returncode,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr + "\nPIPELINE TIMEOUT: stage exceeded 3600 seconds", encoding="utf-8")
        return {
            "stage": stage,
            "command": command,
            "cwd": str(cwd),
            "started_at": utc_now(),
            "exit_code": 124,
            "timeout": True,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }


def run_pipeline(selected: Iterable[str]) -> dict:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "started_at": utc_now(),
        "status": "running",
        "stages": [],
        "selected": list(selected),
        "run_dir": str(run_dir),
    }

    previous_failures: list[str] = []
    for stage in STAGES:
        if stage not in manifest["selected"]:
            continue

        pre_errors = preflight(stage)
        if pre_errors:
            result = {
                "stage": stage,
                "status": "blocked",
                "preflight_errors": pre_errors,
                "started_at": utc_now(),
            }
            manifest["stages"].append(result)
            previous_failures.append(stage)
            break

        cwd = DARPAN_ROOT / stage
        result = run_command(stage_commands(stage)[0], cwd, run_dir, stage)
        result["status"] = "passed" if result["exit_code"] == 0 else "failed"

        if result["exit_code"] == 0:
            gate_errors = artifact_gate(stage)
            if gate_errors:
                result["status"] = "gate_failed"
                result["gate_errors"] = gate_errors

        if result["status"] != "passed":
            previous_failures.append(stage)

        manifest["stages"].append(result)
        if previous_failures:
            break

    manifest["finished_at"] = utc_now()
    manifest["status"] = "passed" if not previous_failures else "failed"

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    latest_path = OUTPUT_ROOT / "latest.json"
    latest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if previous_failures:
        alert_path = run_dir / "failure_alert.txt"
        lines = [f"DARPAN pipeline failed: {run_id}", "", f"Failed stage: {previous_failures[-1]}"]
        for stage_result in manifest["stages"]:
            if stage_result.get("status") != "passed":
                lines.append("")
                lines.append(json.dumps(stage_result, indent=2))
        alert_path.write_text("\n".join(lines), encoding="utf-8")

    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description="M4 DARPAN pipeline orchestrator")
    parser.add_argument("--stage", action="append", choices=STAGES,
                        help="Run only this stage. Repeat for multiple stages. Dependencies are still checked.")
    parser.add_argument("--from-stage", choices=STAGES,
                        help="Run the full pipeline starting at this stage")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stage:
        selected = args.stage
    elif args.from_stage:
        start = STAGES.index(args.from_stage)
        selected = STAGES[start:]
    else:
        selected = list(STAGES)

    manifest = run_pipeline(selected)
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
