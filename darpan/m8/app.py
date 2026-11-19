"""M8 — FastAPI API layer for DARPAN.

Read-only JSON API backed by M3 SQLite plus M5/M6/M7 artifacts.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse


ROOT = Path(__file__).resolve().parents[1]
M3_DB = ROOT / "m3" / "outputs" / "darpan.sqlite"
M5_CSV = ROOT / "m5" / "outputs" / "stress_scores.csv"
M6_CSV = ROOT / "m6" / "outputs" / "anomalies.csv"
M7_JSON = ROOT / "m7" / "outputs" / "briefs.json"
M7_DIR = ROOT / "m7" / "outputs"


app = FastAPI(
    title="DARPAN API",
    version="0.1.0",
    description="Bank stress, anomaly, peer comparison, and policy brief API.",
)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


SCORES = read_csv(M5_CSV)
ANOMALIES = read_csv(M6_CSV)
BRIEFS = json.loads(M7_JSON.read_text(encoding="utf-8")) if M7_JSON.exists() else []


@app.get("/health")
def health():
    return {
        "status": "ok",
        "m3_database": M3_DB.exists(),
        "m5_scores": len(SCORES),
        "m6_anomalies": len(ANOMALIES),
        "m7_briefs": len(BRIEFS),
    }


@app.get("/banks")
def list_banks(
    bank_type: Optional[str] = Query(default=None),
    stress_tier: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None, description="Reserved filter; region facts are sparse in M3"),
):
    result = []
    for row in SCORES:
        if bank_type and row["bank_type"].lower() != bank_type.lower():
            continue

        score = optional_float(row["composite_score"])
        tier = "unrated"
        if score is not None:
            tier = "high" if score >= 75 else "moderate" if score >= 50 else "low"
        if stress_tier and tier != stress_tier.lower():
            continue

        result.append({
            "bank_id": row["bank_id"],
            "name": row["bank_name"],
            "type": row["bank_type"],
            "stress_tier": tier,
            "composite_score": score,
            "confidence": row["confidence"],
            "year": row["year"],
        })
    return {"count": len(result), "banks": result}


@app.get("/banks/{bank_id}/stress")
def bank_stress(bank_id: str):
    row = next((r for r in SCORES if r["bank_id"] == bank_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Bank not found")

    score = optional_float(row["composite_score"])
    tier = "unrated" if score is None else "high" if score >= 75 else "moderate" if score >= 50 else "low"

    return {
        "bank_id": row["bank_id"],
        "bank_name": row["bank_name"],
        "bank_type": row["bank_type"],
        "year": row["year"],
        "stress_tier": tier,
        "composite_score": score,
        "components": {
            "complaint_intensity": optional_float(row["complaint_intensity"]),
            "trend_velocity": optional_float(row["trend_velocity"]),
            "resolution_quality": optional_float(row["resolution_quality"]),
            "award_severity": optional_float(row["award_severity"]),
            "concentration_risk": optional_float(row["concentration_risk"]),
        },
        "available_components": optional_int(row["available_components"]),
        "confidence": row["confidence"],
        "evidence": row["evidence"],
    }


@app.get("/banks/{bank_id}/anomalies")
def bank_anomalies(bank_id: str):
    row = next((r for r in SCORES if r["bank_id"] == bank_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Bank not found")

    result = [
        {
            "bank_id": a["bank_id"],
            "year": a["year"],
            "category": a["category"],
            "method": a["method"],
            "anomaly_score": optional_float(a["anomaly_score"]),
            "z_score": optional_float(a["z_score"]),
            "baseline_mean": optional_float(a["baseline_mean"]),
            "observed_value": optional_float(a["observed_value"]),
            "severity": a["severity"],
            "reason": a["reason"],
            "source_context": a["source_context"],
        }
        for a in ANOMALIES
        if a["bank_id"] == bank_id
    ]
    return {"bank_id": bank_id, "count": len(result), "anomalies": result}


@app.get("/analytics/peer-compare")
def peer_compare(bank_type: Optional[str] = Query(default=None)):
    groups: dict[str, list[dict]] = {}
    for row in SCORES:
        if bank_type and row["bank_type"].lower() != bank_type.lower():
            continue
        groups.setdefault(row["bank_type"], []).append({
            "bank_id": row["bank_id"],
            "bank_name": row["bank_name"],
            "composite_score": optional_float(row["composite_score"]),
            "confidence": row["confidence"],
        })

    return {"peer_groups": groups}


@app.get("/briefs/{bank_id}")
def get_brief(bank_id: str):
    brief = next((b for b in BRIEFS if b["bank_id"] == bank_id), None)
    if not brief:
        raise HTTPException(status_code=404, detail="Policy brief not found")
    return brief


@app.get("/briefs/{bank_id}/download", response_class=PlainTextResponse)
def download_brief(bank_id: str):
    md_path = M7_DIR / f"{bank_id}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Markdown brief not found")
    return PlainTextResponse(md_path.read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/analytics/trends/{bank_id}")
def bank_trends(bank_id: str):
    if not M3_DB.exists():
        raise HTTPException(status_code=503, detail="M3 database unavailable")
    con = sqlite3.connect(f"file:{M3_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("""
            SELECT year, SUM(received) AS received, SUM(disposed) AS disposed,
                   SUM(pending_at_year_end) AS pending, SUM(awards_issued) AS awards
            FROM complaints_annual
            WHERE bank_id = ?
            GROUP BY year
            ORDER BY year
        """, (bank_id,)).fetchall()
    finally:
        con.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Trend data not found")
    return {"bank_id": bank_id, "trend": [dict(row) for row in rows]}
