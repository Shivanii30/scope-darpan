"""M0 source/schema drift detection with a persistent accepted baseline."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from config import DARPAN_ROOT, OUTPUT_DIR, SOURCE_DIR, STATE_DIR


BASELINE_PATH = STATE_DIR / "source_schema_baseline.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_snapshot() -> dict:
    inventory = _read_json(DARPAN_ROOT / "m0" / "outputs" / "source_inventory.json")
    strategy_file = DARPAN_ROOT / "m0" / "outputs" / "extraction_strategy_map.csv"
    strategies: dict[str, dict] = {}
    if strategy_file.exists():
        import csv
        with strategy_file.open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                strategies[row["filename"]] = row

    sources = {}
    for row in inventory.get("rows", []):
        name = row["filename"]
        strategy = strategies.get(name, {})
        sources[name] = {
            "reporting_year": row.get("reporting_year"),
            "size_bytes": row.get("size_bytes"),
            "page_count": row.get("page_count"),
            "has_text_layer": row.get("has_text_layer"),
            "text_density": row.get("text_density"),
            "metrics_visible": row.get("metrics_visible", []),
            "format_era": strategy.get("format_era", row.get("format_era")),
            "schema_variant": strategy.get("schema_variant"),
            "extraction_strategy": strategy.get("extraction_strategy", row.get("extraction_strategy")),
            "sha256": _sha256(SOURCE_DIR / name),
        }

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_count": len(sources),
        "sources": sources,
    }


def get_baseline_before_m0() -> dict | None:
    """Use accepted baseline, falling back to the last completed M0 inventory."""
    saved = _read_json(BASELINE_PATH)
    if saved.get("sources"):
        return saved
    previous = current_snapshot()
    return previous if previous.get("sources") else None


def compare(baseline: dict | None, current: dict) -> list[dict]:
    if not baseline:
        return []
    old_sources = baseline.get("sources", {})
    new_sources = current.get("sources", {})
    changes: list[dict] = []

    for name in sorted(new_sources.keys() - old_sources.keys()):
        changes.append({"severity": "critical", "kind": "source_added", "file": name,
                        "detail": f"New PDF detected for reporting year {new_sources[name].get('reporting_year')}"})
    for name in sorted(old_sources.keys() - new_sources.keys()):
        changes.append({"severity": "critical", "kind": "source_missing", "file": name,
                        "detail": "Previously inventoried PDF is missing"})

    critical_fields = ("has_text_layer", "format_era", "schema_variant", "extraction_strategy")
    warning_fields = ("reporting_year", "page_count", "size_bytes", "sha256", "text_density", "metrics_visible")
    for name in sorted(old_sources.keys() & new_sources.keys()):
        old, new = old_sources[name], new_sources[name]
        for field in critical_fields:
            if old.get(field) != new.get(field):
                changes.append({"severity": "critical", "kind": "schema_drift", "file": name,
                                "field": field, "before": old.get(field), "after": new.get(field),
                                "detail": f"{field} changed; parser behavior requires review"})
        for field in warning_fields:
            if old.get(field) != new.get(field):
                changes.append({"severity": "warning", "kind": "source_changed", "file": name,
                                "field": field, "before": old.get(field), "after": new.get(field),
                                "detail": f"Source {field} changed"})

    return changes


def should_block(changes: list[dict], policy: str, accepted: bool) -> bool:
    return policy == "block" and not accepted and any(
        change.get("severity") == "critical" for change in changes
    )


def write_report(baseline: dict | None, current: dict, changes: list[dict], policy: str, accepted: bool) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline_available": baseline is not None,
        "policy": policy,
        "accepted_by_operator": accepted,
        "status": "drift_detected" if changes else "clear",
        "blocked": any(change["severity"] == "critical" for change in changes) and policy == "block" and not accepted,
        "change_count": len(changes),
        "changes": changes,
        "current_source_count": current.get("source_count", 0),
    }
    path = OUTPUT_DIR / "drift_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def accept_baseline(snapshot: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
