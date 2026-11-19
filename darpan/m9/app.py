"""M9 — Streamlit dashboard for DARPAN."""
from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st


API_BASE = os.environ.get("DARPAN_API_URL", "http://127.0.0.1:8000").rstrip("/")


@st.cache_data(ttl=30)
def get_json(path: str, params: dict | None = None):
    response = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="DARPAN", page_icon="🏦", layout="wide")
st.title("DARPAN — RBI Banking Ombudsman Analytics")
st.caption("M9 dashboard · data sourced from the live M8 API")

try:
    health = get_json("/health")
except Exception as exc:
    st.error(f"M8 API unavailable at {API_BASE}: {exc}")
    st.stop()

with st.sidebar:
    st.subheader("API status")
    st.success("Connected")
    st.caption(f"Banks: {health['m5_scores']} · Anomalies: {health['m6_anomalies']} · Briefs: {health['m7_briefs']}")

    bank_type = st.selectbox("Bank type", ["All"] + sorted({row["type"] for row in get_json("/banks")["banks"]}))
    stress_tier = st.selectbox("Stress tier", ["All", "low", "moderate", "high"])

bank_payload = get_json("/banks")
banks = bank_payload["banks"]

filtered = banks
if bank_type != "All":
    filtered = [row for row in filtered if row["type"] == bank_type]
if stress_tier != "All":
    filtered = [row for row in filtered if row["stress_tier"] == stress_tier]

st.subheader("Bank explorer")
if not filtered:
    st.info("No banks match the selected filters.")
    st.stop()

id_to_name = {row["bank_id"]: row["name"] for row in filtered}
selected_name = st.selectbox("Select bank", list(id_to_name.values()))
selected_id = next(bank_id for bank_id, name in id_to_name.items() if name == selected_name)

try:
    stress = get_json(f"/banks/{selected_id}/stress")
    anomaly_payload = get_json(f"/banks/{selected_id}/anomalies")
    trend_payload = get_json(f"/analytics/trends/{selected_id}")
except Exception as exc:
    st.error(f"Unable to load selected bank data: {exc}")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Composite score", "N/A" if stress["composite_score"] is None else f"{stress['composite_score']:.2f}")
col2.metric("Stress tier", stress["stress_tier"].title())
col3.metric("Confidence", stress["confidence"].title())
col4.metric("Anomalies", anomaly_payload["count"])

st.caption(f"Scoring year: {stress['year']} · {stress['evidence']}")

# Components
st.subheader("Stress components")
components = stress["components"]
component_df = pd.DataFrame([
    {"Component": name.replace("_", " ").title(), "Score": value}
    for name, value in components.items()
])
component_df = component_df.dropna(subset=["Score"])
if component_df.empty:
    st.info("No component scores are available in the current M3/M5 data.")
else:
    st.bar_chart(component_df.set_index("Component"), height=260)

# Trend chart
st.subheader("Complaint volume trend")
trend_df = pd.DataFrame(trend_payload["trend"])
if trend_df.empty:
    st.info("No annual trend data is available.")
else:
    trend_df["year_order"] = range(len(trend_df))
    chart_df = trend_df.set_index("year")[["received", "disposed", "pending", "awards"]]
    st.line_chart(chart_df, height=300)

# Peer comparison
st.subheader("Peer comparison")
try:
    peer_payload = get_json("/analytics/peer-compare", {"bank_type": stress["bank_type"]})
    peer_rows = peer_payload["peer_groups"].get(stress["bank_type"], [])
    peer_df = pd.DataFrame(peer_rows)
    if peer_df.empty:
        st.info("No peer data is available.")
    else:
        st.bar_chart(peer_df.set_index("bank_name")[["composite_score"]], height=260)
except Exception as exc:
    st.warning(f"Peer comparison unavailable: {exc}")

# Anomaly timeline
st.subheader("Anomaly timeline")
if anomaly_payload["count"] == 0:
    st.info("No anomalies crossed the M6 threshold.")
else:
    anomaly_df = pd.DataFrame(anomaly_payload["anomalies"])
    for _, row in anomaly_df.iterrows():
        severity = str(row["severity"]).lower()
        icon = "🔴" if severity == "high" else "🟠" if severity == "medium" else "🟡"
        st.markdown(f"**{icon} {row['severity'].title()} · {row['year']} · {row['category']}**")
        st.caption(f"{row['reason']}  |  z-score: {row['z_score']}  |  method: {row['method']}")

# Policy brief
st.subheader("Policy brief")
try:
    brief = get_json(f"/briefs/{selected_id}")
    tab1, tab2 = st.tabs(["Brief", "Download"])
    with tab1:
        st.markdown(brief["markdown"])
    with tab2:
        md_response = requests.get(f"{API_BASE}/briefs/{selected_id}/download", timeout=10)
        md_response.raise_for_status()
        st.download_button(
            "Download Markdown brief",
            data=md_response.text,
            file_name=f"{selected_id}_policy_brief.md",
            mime="text/markdown",
        )
except Exception as exc:
    st.warning(f"Policy brief unavailable: {exc}")

st.divider()
st.caption("Missing component scores are not extrapolated. M9 displays M5/M6/M7 outputs exactly as produced by upstream modules.")
