"""
dashboard/app.py
-----------------
Streamlit dashboard for the Multi-Source Health Data Integration Pipeline.

Data flow (important — read this before changing anything):
    PostgreSQL  --(SQL query)-->  pandas DataFrame  --(st.dataframe/plotly)-->  browser

    The dashboard NEVER reads data/raw/*.csv directly. Every number shown
    here comes from a SQL query against the tables/views that src/load.py
    created. This is deliberate: it proves the ETL pipeline is the single
    source of truth for the dashboard, the same way a real BI tool
    (Metabase, Looker, PowerBI) sits on top of a warehouse rather than
    re-reading a department's original spreadsheets.

Run locally:
    streamlit run dashboard/app.py
Run in Docker:
    started automatically by docker-compose (see docker-compose.yml)
"""

import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

st.set_page_config(
    page_title="Multi-Source Health Data Pipeline",
    page_icon="🏥",
    layout="wide",
)


@st.cache_resource
def get_engine():
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "health_pipeline")
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "postgres")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    return create_engine(url)


@st.cache_data(ttl=60)
def run_query(sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, get_engine())


st.title("🏥 Multi-Source Health Data Integration Pipeline")
st.caption(
    "A small, realistic ETL project demonstrating an end-to-end data "
    "engineering workflow — not a big-data or enterprise-scale system. "
    "All figures below are computed live from PostgreSQL, which was "
    "populated by the pipeline in `src/pipeline.py`."
)

# ---------------------------------------------------------------------------
# Guard: if the pipeline hasn't been run yet, tables won't exist. Fail
# clearly instead of showing a confusing stack trace.
# ---------------------------------------------------------------------------
try:
    totals = run_query("""
        SELECT
            (SELECT COUNT(*) FROM facilities) AS total_facilities,
            (SELECT COUNT(*) FROM patient_visits) AS total_visits,
            (SELECT COUNT(*) FROM disease_cases) AS total_cases
    """).iloc[0]
except Exception as exc:
    st.error(
        "Could not read from the database. Have you run the ETL pipeline "
        "yet? Try `python src/pipeline.py` (or `docker compose up --build`)."
    )
    st.exception(exc)
    st.stop()

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Facilities", int(totals["total_facilities"]))
col2.metric("Total Patient Visits", int(totals["total_visits"]))
col3.metric("Total Disease Cases", int(totals["total_cases"]))

latest_month = run_query("""
    SELECT MAX(case_month) AS m FROM visit_disease_summary
""")["m"].iloc[0]
col4.metric("Latest Data Month", latest_month or "N/A")

st.divider()

# ---------------------------------------------------------------------------
# Trend over time
# ---------------------------------------------------------------------------
st.subheader("Monthly Patient Visit Trend")
visit_trend = run_query("SELECT * FROM view_monthly_visit_trend ORDER BY visit_month")
st.line_chart(visit_trend.set_index("visit_month"))

st.subheader("Monthly Disease Case Trend")
case_trend = run_query("""
    SELECT case_month, SUM(case_count) AS total_cases
    FROM visit_disease_summary
    GROUP BY case_month ORDER BY case_month
""")
st.line_chart(case_trend.set_index("case_month"))

st.divider()

# ---------------------------------------------------------------------------
# Regional + disease breakdowns
# ---------------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Visits by Region")
    by_region = run_query("SELECT * FROM view_visits_by_region ORDER BY visit_count DESC")
    st.bar_chart(by_region.set_index("region"))

with right:
    st.subheader("Cases by Disease")
    by_disease = run_query("SELECT * FROM view_cases_by_disease ORDER BY case_count DESC")
    st.bar_chart(by_disease.set_index("disease_name")["case_count"])
    st.dataframe(by_disease, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Top facilities + age breakdown
# ---------------------------------------------------------------------------
left2, right2 = st.columns(2)

with left2:
    st.subheader("Top Facilities by Visit Count")
    top_facilities = run_query("SELECT * FROM view_top_facilities LIMIT 10")
    st.dataframe(top_facilities, use_container_width=True, hide_index=True)

with right2:
    st.subheader("Visits by Age Group")
    age_breakdown = run_query("""
        SELECT age_group, COUNT(*) AS visit_count
        FROM patient_visits
        WHERE age_group IS NOT NULL
        GROUP BY age_group
        ORDER BY age_group
    """)
    st.bar_chart(age_breakdown.set_index("age_group"))

st.divider()

# ---------------------------------------------------------------------------
# Raw indicator explorer
# ---------------------------------------------------------------------------
st.subheader("Monthly Indicators (latest value per region)")
latest_indicators = run_query("""
    SELECT DISTINCT ON (region, indicator_name)
        region, indicator_name, month, indicator_value
    FROM monthly_indicators
    ORDER BY region, indicator_name, month DESC
""")
st.dataframe(latest_indicators, use_container_width=True, hide_index=True)

st.caption(
    "Data source: synthetic CSV files generated by src/generate_data.py — "
    "not real patient data."
)
