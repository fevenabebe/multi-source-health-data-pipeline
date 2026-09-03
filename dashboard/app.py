"""
dashboard/app.py
-----------------
Streamlit dashboard for the Multi-Source Health Data Integration Pipeline.

The ETL pipeline cleans and prepares the data in data/bi/.
The online Streamlit dashboard reads those BI-ready outputs directly,
making the demo deployable without a PostgreSQL server.

PostgreSQL remains part of the project's production-oriented ETL architecture.
"""

from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Multi-Source Health Data Pipeline",
    page_icon="🏥",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
BI_DIR = BASE_DIR / "data" / "bi"


@st.cache_data
def load_data():
    facilities = pd.read_csv(BI_DIR / "facilities_clean.csv")
    patient_visits = pd.read_csv(BI_DIR / "patient_visits_clean.csv")
    disease_cases = pd.read_csv(BI_DIR / "disease_cases_clean.csv")
    monthly_indicators = pd.read_csv(BI_DIR / "monthly_indicators_clean.csv")
    visit_disease_summary = pd.read_csv(
        BI_DIR / "visit_disease_summary_clean.csv"
    )

    return (
        facilities,
        patient_visits,
        disease_cases,
        monthly_indicators,
        visit_disease_summary,
    )


try:
    (
        facilities,
        patient_visits,
        disease_cases,
        monthly_indicators,
        visit_disease_summary,
    ) = load_data()

except Exception as exc:
    st.error(
        "Could not load the BI-ready datasets. "
        "Make sure the files exist in `data/bi/`."
    )
    st.exception(exc)
    st.stop()


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

st.title("🏥 Multi-Source Health Data Integration Pipeline")

st.caption(
    "A small, realistic ETL project demonstrating an end-to-end data "
    "engineering workflow — not a big-data or enterprise-scale system. "
    "The dashboard uses cleaned BI-ready outputs produced by the ETL "
    "transformation stage."
)


# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total Facilities",
    len(facilities),
)

col2.metric(
    "Total Patient Visits",
    len(patient_visits),
)

col3.metric(
    "Total Disease Cases",
    len(disease_cases),
)

if "case_month" in visit_disease_summary.columns:
    latest_month = visit_disease_summary["case_month"].dropna().max()
else:
    latest_month = "N/A"

col4.metric(
    "Latest Data Month",
    latest_month if pd.notna(latest_month) else "N/A",
)


st.divider()


# ---------------------------------------------------------------------------
# Monthly trends
# ---------------------------------------------------------------------------

st.subheader("Monthly Patient Visit Trend")

if "visit_date" in patient_visits.columns:
    patient_visits["visit_month"] = pd.to_datetime(
        patient_visits["visit_date"],
        errors="coerce",
    ).dt.to_period("M").astype(str)

    visit_trend = (
        patient_visits.dropna(subset=["visit_month"])
        .groupby("visit_month")
        .size()
        .reset_index(name="visit_count")
    )

    visit_trend = visit_trend.sort_values("visit_month")

    st.line_chart(
        visit_trend.set_index("visit_month")["visit_count"]
    )


st.subheader("Monthly Disease Case Trend")

if {"case_month", "case_count"}.issubset(visit_disease_summary.columns):
    case_trend = (
        visit_disease_summary.groupby("case_month", as_index=False)[
            "case_count"
        ]
        .sum()
        .sort_values("case_month")
    )

    st.line_chart(
        case_trend.set_index("case_month")["case_count"]
    )


st.divider()


# ---------------------------------------------------------------------------
# Regional + disease breakdowns
# ---------------------------------------------------------------------------

left, right = st.columns(2)


with left:
    st.subheader("Visits by Region")

    if "region" in patient_visits.columns:
        by_region = (
            patient_visits.groupby("region")
            .size()
            .reset_index(name="visit_count")
            .sort_values("visit_count", ascending=False)
        )

        st.bar_chart(
            by_region.set_index("region")["visit_count"]
        )


with right:
    st.subheader("Cases by Disease")

    if {"disease_name", "case_count"}.issubset(
        visit_disease_summary.columns
    ):
        by_disease = (
            visit_disease_summary.groupby("disease_name", as_index=False)[
                "case_count"
            ]
            .sum()
            .sort_values("case_count", ascending=False)
        )

        st.bar_chart(
            by_disease.set_index("disease_name")["case_count"]
        )

        st.dataframe(
            by_disease,
            use_container_width=True,
            hide_index=True,
        )


st.divider()


# ---------------------------------------------------------------------------
# Top facilities + age breakdown
# ---------------------------------------------------------------------------

left2, right2 = st.columns(2)


with left2:
    st.subheader("Top Facilities by Visit Count")

    if "facility_id" in patient_visits.columns:
        top_facilities = (
            patient_visits.groupby("facility_id")
            .size()
            .reset_index(name="visit_count")
            .sort_values("visit_count", ascending=False)
            .head(10)
        )

        if "facility_name" in facilities.columns:
            top_facilities = top_facilities.merge(
                facilities[["facility_id", "facility_name"]],
                on="facility_id",
                how="left",
            )

            top_facilities = top_facilities[
                ["facility_id", "facility_name", "visit_count"]
            ]

        st.dataframe(
            top_facilities,
            use_container_width=True,
            hide_index=True,
        )


with right2:
    st.subheader("Visits by Age Group")

    if "age_group" in patient_visits.columns:
        age_breakdown = (
            patient_visits.dropna(subset=["age_group"])
            .groupby("age_group")
            .size()
            .reset_index(name="visit_count")
            .sort_values("age_group")
        )

        st.bar_chart(
            age_breakdown.set_index("age_group")["visit_count"]
        )


st.divider()


# ---------------------------------------------------------------------------
# Monthly indicators
# ---------------------------------------------------------------------------

st.subheader("Monthly Indicators — Latest Value per Region")

if {"region", "indicator_name", "month", "indicator_value"}.issubset(
    monthly_indicators.columns
):

    indicators = monthly_indicators.copy()

    indicators["month"] = pd.to_datetime(
        indicators["month"],
        errors="coerce",
    )

    latest_indicators = (
        indicators.sort_values("month")
        .drop_duplicates(
            subset=["region", "indicator_name"],
            keep="last",
        )
        .sort_values(["region", "indicator_name"])
    )

    latest_indicators["month"] = (
        latest_indicators["month"]
        .dt.strftime("%Y-%m")
    )

    st.dataframe(
        latest_indicators,
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------------------------
# Data quality / pipeline summary
# ---------------------------------------------------------------------------

st.divider()

st.subheader("Pipeline Output Summary")

summary = pd.DataFrame(
    {
        "Dataset": [
            "Facilities",
            "Patient Visits",
            "Disease Cases",
            "Monthly Indicators",
            "Visit-Disease Summary",
        ],
        "Rows": [
            len(facilities),
            len(patient_visits),
            len(disease_cases),
            len(monthly_indicators),
            len(visit_disease_summary),
        ],
    }
)

st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True,
)


st.caption(
    "Data source: synthetic CSV files generated by "
    "`src/generate_data.py` — not real patient data."
)
