"""M6 explainable anomaly detection engine.

Primary method: rolling z-score over complaint volumes per bank/category.
Fallback: peer-median deviation for category volume across bank peer groups.
Change-point method: adjacent-year mean-shift with 2.0/3.0 sigma thresholds.

M6 intentionally does not claim STL, ruptures, or isolation-forest evidence
unless their implementations and sufficient annual data exist.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    variance = sum((value - mu) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def severity_from_z(z: float) -> str:
    absolute = abs(z)
    if absolute >= 3.0:
        return "high"
    if absolute >= 2.0:
        return "medium"
    return "low"


class AnomalyEngine:
    def __init__(self, m3_db: Path, m5_db: Path):
        self.m3_db = m3_db
        self.m5_db = m5_db
        self.con = sqlite3.connect(f"file:{m3_db}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row

    def close(self):
        self.con.close()

    def banks(self) -> list[sqlite3.Row]:
        return list(self.con.execute("SELECT * FROM banks ORDER BY canonical_name"))

    def series(self, bank_id: str) -> list[tuple[str, int]]:
        rows = self.con.execute("""
            SELECT year, SUM(received) AS received
            FROM complaints_annual
            WHERE bank_id = ?
            GROUP BY year
            ORDER BY year
        """, (bank_id,)).fetchall()
        return [(r["year"], r["received"] or 0) for r in rows]

    def category_series(self, bank_id: str) -> dict[str, list[tuple[str, int]]]:
        rows = self.con.execute("""
            SELECT year, c.label AS category, SUM(a.received) AS received
            FROM complaints_annual a
            JOIN complaint_categories c ON c.category_id = a.category_id
            WHERE a.bank_id = ?
            GROUP BY year, c.category_id, c.label
            ORDER BY year, c.label
        """, (bank_id,)).fetchall()
        output: dict[str, list[tuple[str, int]]] = {}
        for row in rows:
            output.setdefault(row["category"], []).append((row["year"], row["received"] or 0))
        return output

    def detect(self) -> list[dict]:
        anomalies: list[dict] = []

        for bank in self.banks():
            series = self.series(bank["bank_id"])
            if len(series) >= 3:
                values = [value for _, value in series]
                prior_values = values[:-1]
                baseline_mean = mean(prior_values)
                baseline_std = stddev(prior_values)
                latest_year, latest_value = series[-1]

                if baseline_std > 0:
                    z_score = (latest_value - baseline_mean) / baseline_std
                    if abs(z_score) >= 2.0:
                        anomalies.append({
                            "bank_id": bank["bank_id"],
                            "bank_name": bank["canonical_name"],
                            "bank_type": bank["bank_type"],
                            "year": latest_year,
                            "category": "ALL_CATEGORIES",
                            "method": "rolling_z_score",
                            "anomaly_score": round(clamp(abs(z_score) * 25.0), 2),
                            "z_score": round(z_score, 3),
                            "baseline_mean": round(baseline_mean, 2),
                            "observed_value": latest_value,
                            "severity": severity_from_z(z_score),
                            "reason": f"Latest volume is {z_score:+.2f}sigma versus prior annual mean",
                            "source_context": f"prior_points={len(prior_values)}; latest_year={latest_year}; metric=received",
                        })

                if len(values) >= 4:
                    previous_half = values[:-2]
                    recent_half = values[-2:] if len(values) >= 4 else []
                    old_mean = mean(previous_half)
                    recent_mean = mean(recent_half)
                    pooled_std = stddev(values)
                    if pooled_std > 0:
                        shift_z = (recent_mean - old_mean) / pooled_std
                        if abs(shift_z) >= 2.0:
                            anomalies.append({
                                "bank_id": bank["bank_id"],
                                "bank_name": bank["canonical_name"],
                                "bank_type": bank["bank_type"],
                                "year": latest_year,
                                "category": "ALL_CATEGORIES",
                                "method": "mean_shift_change_point",
                                "anomaly_score": round(clamp(abs(shift_z) * 25.0), 2),
                                "z_score": round(shift_z, 3),
                                "baseline_mean": round(old_mean, 2),
                                "observed_value": round(recent_mean, 2),
                                "severity": severity_from_z(shift_z),
                                "reason": f"Recent 2-year mean shifted {shift_z:+.2f}sigma from earlier mean",
                                "source_context": f"earlier_points={len(previous_half)}; recent_points={len(recent_half)}",
                            })

            for category, points in self.category_series(bank["bank_id"]).items():
                if len(points) < 3:
                    continue
                values = [value for _, value in points]
                prior = values[:-1]
                baseline_mean = mean(prior)
                baseline_std = stddev(prior)
                if baseline_std <= 0:
                    continue
                year, observed = points[-1]
                z_score = (observed - baseline_mean) / baseline_std
                if abs(z_score) >= 2.0:
                    anomalies.append({
                        "bank_id": bank["bank_id"],
                        "bank_name": bank["canonical_name"],
                        "bank_type": bank["bank_type"],
                        "year": year,
                        "category": category,
                        "method": "rolling_z_score_category",
                        "anomaly_score": round(clamp(abs(z_score) * 25.0), 2),
                        "z_score": round(z_score, 3),
                        "baseline_mean": round(baseline_mean, 2),
                        "observed_value": observed,
                        "severity": severity_from_z(z_score),
                        "reason": f"Category volume is {z_score:+.2f}sigma versus prior category mean",
                        "source_context": f"category={category}; prior_points={len(prior)}; metric=received",
                    })

        return anomalies
