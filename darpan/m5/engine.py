"""M5 stress score engine.

The engine is deliberately conservative. It computes only sub-scores supported
by available M3 evidence and marks missing components rather than inventing
financial or maintainability data.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path


WEIGHTS = {
    "intensity": 0.25,
    "trend_velocity": 0.20,
    "resolution_quality": 0.20,
    "award_severity": 0.20,
    "concentration_risk": 0.15,
}


@dataclass
class ScoreRow:
    bank_id: str
    bank_name: str
    bank_type: str
    year: str
    complaint_intensity: float | None
    trend_velocity: float | None
    resolution_quality: float | None
    award_severity: float | None
    concentration_risk: float | None
    composite_score: float | None
    available_components: int
    confidence: str
    evidence: str


def percentile_rank(values: list[float], value: float) -> float:
    if not values:
        return 50.0
    values = [v for v in values if math.isfinite(v)]
    if not values:
        return 50.0
    lower = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return 100.0 * (lower + 0.5 * equal) / len(values)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def fiscal_sort_key(year: str) -> tuple[int, int]:
    parts = year.split("-")
    start = int(parts[0])
    end = int(parts[1]) if len(parts) > 1 else start
    end = end + 2000 if end < 100 else end
    return start, end


class StressEngine:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row

    def close(self):
        self.con.close()

    def banks(self) -> list[sqlite3.Row]:
        return list(self.con.execute("SELECT * FROM banks ORDER BY canonical_name"))

    def bank_financials_available(self) -> bool:
        row = self.con.execute("SELECT COUNT(*) AS n FROM bank_financials").fetchone()
        return bool(row["n"])

    def complaint_series(self, bank_id: str) -> list[tuple[str, int, int, float]]:
        rows = self.con.execute("""
            SELECT year,
                   SUM(received) AS received,
                   SUM(disposed) AS disposed,
                   SUM(award_amount) AS award_amount
            FROM complaints_annual
            WHERE bank_id = ?
            GROUP BY year
            ORDER BY year
        """, (bank_id,)).fetchall()
        return [(r["year"], r["received"] or 0, r["disposed"] or 0,
                 r["award_amount"] or 0.0) for r in rows]

    def has_resolution_evidence(self, bank_id: str) -> bool:
        rows = self.complaint_series(bank_id)
        return any(received > 0 or disposed > 0 for _, received, disposed, _ in rows)

    def peer_values(self, bank_type: str, bank_id: str | None = None) -> list[str]:
        return [r["bank_id"] for r in self.con.execute(
            "SELECT bank_id FROM banks WHERE bank_type = ? ORDER BY bank_id",
            (bank_type,),
        )]

    def trend_score(self, series: list[tuple[str, int, int, float]]) -> float | None:
        ordered = sorted(series, key=lambda r: fiscal_sort_key(r[0]))
        if len(ordered) < 2:
            return None
        latest = ordered[-1][1]
        previous = ordered[-2][1]
        if previous <= 0:
            return None
        yoy = (latest - previous) / previous
        # Growth is stress-positive; 50% or greater YoY growth = 100.
        return clamp(yoy * 200.0)

    def resolution_score(self, series: list[tuple[str, int, int, float]]) -> float | None:
        ordered = sorted(series, key=lambda r: fiscal_sort_key(r[0]))
        if not ordered:
            return None
        _, received, disposed, _ = ordered[-1]
        if received <= 0 or disposed <= 0:
            return None
        disposal_rate = disposed / received
        # Lower disposal rate is higher stress.
        return clamp(100.0 * (1.0 - min(disposal_rate, 1.0)))

    def award_score(self, series: list[tuple[str, int, int, float]], peer_awards: dict[str, list[float]]) -> float | None:
        ordered = sorted(series, key=lambda r: fiscal_sort_key(r[0]))
        if not ordered:
            return None
        current_award = ordered[-1][3]
        peer_values = peer_awards[""] if "" in peer_awards else []
        if not peer_values:
            return None
        return percentile_rank(peer_values, current_award)

    def concentration_score(self, bank_id: str) -> float | None:
        rows = self.con.execute("""
            SELECT category_id, SUM(received) AS received
            FROM complaints_annual
            WHERE bank_id = ? AND category_id IS NOT NULL
            GROUP BY category_id
        """, (bank_id,)).fetchall()
        if not rows:
            return None
        values = [r["received"] or 0 for r in rows]
        total = sum(values)
        if total <= 0:
            return None
        shares = [v / total for v in values]
        # Herfindahl-Hirschman Index: concentration is stress-positive.
        hhi = sum(s * s for s in shares)
        category_count = len(shares)
        if category_count <= 1:
            hhi_normalized = 1.0
        else:
            hhi_normalized = (hhi - 1.0 / category_count) / (1.0 - 1.0 / category_count)
        return clamp(hhi_normalized * 100.0)

    def run(self) -> list[dict]:
        banks = self.banks()
        latest_awards: dict[str, float] = {}
        for bank in banks:
            series = self.complaint_series(bank["bank_id"])
            if series:
                latest_awards[bank["bank_id"]] = sorted(series, key=lambda r: fiscal_sort_key(r[0]))[-1][3]

        peer_award_lists: dict[str, list[float]] = {}
        for bank_type in sorted({b["bank_type"] for b in banks}):
            peer_ids = [b["bank_id"] for b in banks if b["bank_type"] == bank_type]
            peer_award_lists[bank_type] = [latest_awards[b] for b in peer_ids if b in latest_awards]

        output: list[dict] = []
        for bank in banks:
            series = self.complaint_series(bank["bank_id"])
            if not series:
                continue
            latest = sorted(series, key=lambda r: fiscal_sort_key(r[0]))[-1]

            intensity = None  # Bank financial normalization unavailable until M10/DBIE data exists.
            trend = self.trend_score(series)
            resolution = self.resolution_score(series)
            award_values = peer_award_lists.get(bank["bank_type"], [])
            current_award = latest[3]
            award = percentile_rank(award_values, current_award) if len(award_values) >= 2 else None
            concentration = self.concentration_score(bank["bank_id"])

            components = {
                "intensity": intensity,
                "trend_velocity": trend,
                "resolution_quality": resolution,
                "award_severity": award,
                "concentration_risk": concentration,
            }
            available = {k: v for k, v in components.items() if v is not None}

            if available:
                # Renormalize available weights so missing components do not reduce the score.
                normalized_weight = sum(WEIGHTS[k] for k in available)
                composite = sum(components[k] * WEIGHTS[k] for k in available) / normalized_weight
            else:
                composite = None

            component_count = len(available)
            if component_count >= 4:
                confidence = "high"
            elif component_count >= 2:
                confidence = "medium"
            else:
                confidence = "low"

            evidence_parts = [
                f"year={latest[0]}",
                f"received={latest[1]}",
                f"disposed={latest[2]}",
                f"series_points={len(series)}",
                f"peer_group={bank['bank_type']}",
                f"peer_count={len(peer_award_lists.get(bank['bank_type'], []))}",
            ]
            if intensity is None:
                evidence_parts.append("intensity=unavailable_bank_financials_empty")
            if resolution is None:
                evidence_parts.append("resolution_quality=unavailable_disposal_not_populated")
            if award is None:
                evidence_parts.append("award_severity=unavailable_fewer_than_two_peer_banks")

            output.append({
                "bank_id": bank["bank_id"],
                "bank_name": bank["canonical_name"],
                "bank_type": bank["bank_type"],
                "year": latest[0],
                "complaint_intensity": None if intensity is None else round(intensity, 2),
                "trend_velocity": None if trend is None else round(trend, 2),
                "resolution_quality": None if resolution is None else round(resolution, 2),
                "award_severity": None if award is None else round(award, 2),
                "concentration_risk": None if concentration is None else round(concentration, 2),
                "composite_score": None if composite is None else round(clamp(composite), 2),
                "available_components": component_count,
                "confidence": confidence,
                "evidence": "; ".join(evidence_parts),
            })

        return output
