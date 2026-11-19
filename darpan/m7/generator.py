"""M7 fixed-schema policy brief generator.

The generator is deterministic and local: it narrates only precomputed M5/M6
values and never calculates or invents complaint metrics.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
M3_DB = ROOT / "m3" / "outputs" / "darpan.sqlite"
M5_CSV = ROOT / "m5" / "outputs" / "stress_scores.csv"
M6_CSV = ROOT / "m6" / "outputs" / "anomalies.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def format_number(value: str | None) -> str:
    if value in (None, ""):
        return "Not available"
    try:
        number = float(value)
        return f"{number:.2f}"
    except ValueError:
        return str(value)


def tier(score: str | None) -> str:
    if score in (None, ""):
        return "unrated"
    value = float(score)
    if value >= 75:
        return "high stress"
    if value >= 50:
        return "moderate stress"
    return "lower stress"


def peer_comparison(rows: list[dict], row: dict) -> str:
    peers = [r for r in rows if r["bank_type"] == row["bank_type"] and r["bank_id"] != row["bank_id"]]
    if not peers:
        return f"This bank is the sole available member of its {row['bank_type']} peer group."

    peer_scores = [float(r["composite_score"]) for r in peers if r["composite_score"]]
    if not peer_scores:
        return f"Peer comparison is limited because the {row['bank_type']} peers have no complete composite scores."
    own = float(row["composite_score"]) if row["composite_score"] else None
    if own is None:
        return f"Peer comparison is unavailable because this bank has no composite score."
    peer_mean = sum(peer_scores) / len(peer_scores)
    direction = "above" if own > peer_mean else "below"
    return f"The bank's composite score is {direction} the peer mean of {peer_mean:.2f}."


def generate_brief(row: dict, scores: list[dict], anomalies: list[dict]) -> dict:
    bank_id = row["bank_id"]
    bank_name = row["bank_name"]
    year = row["year"]
    bank_anomalies = [a for a in anomalies if a["bank_id"] == bank_id]

    executive = (
        f"{bank_name} is classified as {tier(row['composite_score'])} at a composite score of "
        f"{format_number(row['composite_score'])}/100 for {year}. The result has "
        f"{row['confidence']} confidence because {row['available_components']} of 5 stress components are available."
    )

    trend = "Trend velocity is "
    if row["trend_velocity"]:
        trend += f"{format_number(row['trend_velocity'])}/100. "
    else:
        trend += "not available. "
    trend += (
        f"Complaint-volume evidence in the M5 row covers {year}. "
        "No raw complaint volume is restated in this brief beyond the M5 evidence string."
    )

    rationale_parts = []
    labels = (
        ("Complaint intensity", row["complaint_intensity"]),
        ("Trend velocity", row["trend_velocity"]),
        ("Resolution quality", row["resolution_quality"]),
        ("Award severity", row["award_severity"]),
        ("Concentration risk", row["concentration_risk"]),
    )
    for label, value in labels:
        if value:
            rationale_parts.append(f"{label}: {format_number(value)}/100")
    rationale = "Available sub-components - " + "; ".join(rationale_parts) + "."

    missing = [label for label, value in labels if not value]
    if missing:
        rationale += " Missing components: " + ", ".join(missing) + "."

    peer = peer_comparison(scores, row)

    if bank_anomalies:
        anomaly_lines = []
        for anomaly in bank_anomalies:
            anomaly_lines.append(
                f"- {anomaly['severity'].upper()} {anomaly['method']} anomaly in {anomaly['year']} "
                f"for {anomaly['category']}: {anomaly['reason']} "
                f"({anomaly['source_context']})."
            )
        anomalies_section = "\n".join(anomaly_lines)
    else:
        anomalies_section = "No M6 anomaly crossed the implemented 2σ threshold for this bank."

    provenance = (
        "Data provenance: M3 complaints_annual and bank dimensions; M5 stress_scores; "
        "M6 anomalies; source year(s) limited by the M5/M6 evidence fields. "
        "Complaint-intensity and resolution fields remain unavailable where the underlying M3 tables are empty or unpopulated."
    )

    markdown = "\n".join([
        f"# Policy Brief - {bank_name}", "",
        "## Executive Summary", executive, "",
        "## Trend Analysis", trend, "",
        "## Stress Score Rationale", rationale, "",
        "## Peer Positioning", peer, "",
        "## Anomalies Flagged", anomalies_section, "",
        "## Data Provenance", provenance, "",
    ])

    return {
        "bank_id": bank_id,
        "bank_name": bank_name,
        "bank_type": row["bank_type"],
        "year": year,
        "executive_summary": executive,
        "trend_analysis": trend,
        "stress_score_rationale": rationale,
        "peer_positioning": peer,
        "anomalies_flagged": bank_anomalies,
        "anomalies_markdown": anomalies_section,
        "data_provenance": provenance,
        "markdown": markdown,
    }
