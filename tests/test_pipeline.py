"""
test_pipeline.py
-----------------
Pytest tests for the transform stage (and a couple of extract checks).

Why test transform() so heavily and not load()?
    transform.py contains all of the actual business logic (cleaning
    rules, standardization, joins) — it's pure functions of DataFrames in,
    DataFrames out, so it's fast and easy to test without a real database.
    load.py mostly delegates to pandas/SQLAlchemy and needs a live
    PostgreSQL connection, so it's exercised by actually running the
    pipeline (locally or in Docker) rather than in unit tests. This mirrors
    a common real-world split: unit-test your logic, integration-test your
    infrastructure glue.

Run:
    pytest tests/ -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transform import (  # noqa: E402
    standardize_region,
    standardize_gender,
    parse_messy_date,
    clean_age,
    make_age_group,
    clean_facilities,
    clean_patient_visits,
    clean_disease_cases,
    clean_monthly_indicators,
    build_visit_disease_summary,
)


# ---------------------------------------------------------------------------
# standardize_region
# ---------------------------------------------------------------------------
def test_standardize_region_maps_known_aliases():
    s = pd.Series(["AA", "addis ababa", "Addis Ababa", "oromia", "ORO"])
    result = standardize_region(s)
    assert list(result) == ["Addis Ababa", "Addis Ababa", "Addis Ababa",
                             "Oromia", "Oromia"]


def test_standardize_region_keeps_unknown_value_unchanged():
    s = pd.Series(["Mars"])
    assert standardize_region(s).iloc[0] == "Mars"


# ---------------------------------------------------------------------------
# standardize_gender
# ---------------------------------------------------------------------------
def test_standardize_gender_maps_variants():
    s = pd.Series(["M", "male", "Female", "f", None])
    result = standardize_gender(s)
    assert list(result) == ["Male", "Male", "Female", "Female", "Unknown"]


# ---------------------------------------------------------------------------
# parse_messy_date
# ---------------------------------------------------------------------------
def test_parse_messy_date_handles_multiple_formats():
    s = pd.Series(["2024-01-05", "05/01/2024", "01-05-2024", "5 Jan 2024"])
    result = parse_messy_date(s)
    assert result.notna().all()
    # '2024-01-05' (%Y-%m-%d) and '01-05-2024' (%m-%d-%Y) both mean Jan 5, 2024
    assert result.iloc[0] == pd.Timestamp("2024-01-05")
    assert result.iloc[2] == pd.Timestamp("2024-01-05")
    assert result.iloc[3] == pd.Timestamp("2024-01-05")


def test_parse_messy_date_unparseable_becomes_nat():
    s = pd.Series(["not a date"])
    result = parse_messy_date(s)
    assert result.isna().all()


# ---------------------------------------------------------------------------
# clean_age / make_age_group
# ---------------------------------------------------------------------------
def test_clean_age_nulls_out_of_range_values():
    s = pd.Series(["30", "-3", "150", "", None])
    result = clean_age(s)
    assert result.iloc[0] == 30
    assert pd.isna(result.iloc[1])  # negative age
    assert pd.isna(result.iloc[2])  # impossible age
    assert pd.isna(result.iloc[3])  # blank
    assert pd.isna(result.iloc[4])  # missing


def test_make_age_group_buckets_correctly():
    ages = pd.Series([2, 10, 25, 45, 70])
    groups = make_age_group(ages)
    assert list(groups.astype(str)) == ["0-4", "5-17", "18-39", "40-59", "60+"]


# ---------------------------------------------------------------------------
# Per-source cleaning functions (using small hand-built DataFrames so tests
# don't depend on the randomly generated synthetic data files)
# ---------------------------------------------------------------------------
def test_clean_facilities_drops_exact_duplicates():
    df = pd.DataFrame({
        "facility_id": ["FAC001", "FAC001", "FAC002"],
        "facility_name": ["A Hospital", "A Hospital", "B Clinic"],
        "region": ["AA", "AA", "oromia"],
        "facility_type": ["Hospital", "Hospital", "Clinic"],
        "ownership": ["Government", "Government", "Private"],
    })
    result = clean_facilities(df)
    assert len(result) == 2
    assert set(result["facility_id"]) == {"FAC001", "FAC002"}
    assert result.loc[result["facility_id"] == "FAC001", "region"].iloc[0] == "Addis Ababa"


def test_clean_facilities_has_expected_columns():
    df = pd.DataFrame({
        "facility_id": ["FAC001"], "facility_name": ["A"], "region": ["AA"],
        "facility_type": ["Hospital"], "ownership": ["Government"],
    })
    result = clean_facilities(df)
    assert set(result.columns) == {
        "facility_id", "facility_name", "region", "facility_type", "ownership"
    }


def test_clean_patient_visits_drops_rows_missing_facility_or_date():
    df = pd.DataFrame({
        "visit_id": ["V1", "V2"],
        "patient_id": ["P1", "P2"],
        "facility_code": ["FAC001", None],  # V2 has no facility -> should be dropped
        "region_name": ["AA", "AA"],
        "visit_date": ["2024-01-01", "2024-01-02"],
        "age": ["30", "40"],
        "gender": ["M", "F"],
    })
    result = clean_patient_visits(df)
    assert len(result) == 1
    assert result.iloc[0]["visit_id"] == "V1"


def test_clean_disease_cases_resolves_facility_name_to_id():
    facilities = pd.DataFrame({
        "facility_id": ["FAC001"], "facility_name": ["City Hospital"],
        "region": ["Addis Ababa"], "facility_type": ["Hospital"],
        "ownership": ["Government"],
    })
    cases = pd.DataFrame({
        "case_id": ["C1"], "patient_id": ["P1"], "disease_name": ["Malaria"],
        "facility": ["City Hospital"], "diagnosis_date": ["2024-01-01"],
        "severity": [None],
    })
    result = clean_disease_cases(cases, facilities)
    assert result.iloc[0]["facility_id"] == "FAC001"
    assert result.iloc[0]["severity"] == "Unknown"  # missing -> filled


def test_clean_disease_cases_drops_unmatched_facility_names():
    facilities = pd.DataFrame({
        "facility_id": ["FAC001"], "facility_name": ["City Hospital"],
        "region": ["Addis Ababa"], "facility_type": ["Hospital"],
        "ownership": ["Government"],
    })
    cases = pd.DataFrame({
        "case_id": ["C1"], "patient_id": ["P1"], "disease_name": ["Malaria"],
        "facility": ["Nonexistent Clinic"], "diagnosis_date": ["2024-01-01"],
        "severity": ["Mild"],
    })
    result = clean_disease_cases(cases, facilities)
    assert len(result) == 0


def test_clean_monthly_indicators_drops_non_numeric_values():
    df = pd.DataFrame({
        "month": ["2024-01", "2024-01"],
        "region": ["AA", "AA"],
        "indicator_name": ["Bed Occupancy Rate (%)", "Bed Occupancy Rate (%)"],
        "indicator_value": ["55.5", "not_a_number"],
    })
    result = clean_monthly_indicators(df)
    assert len(result) == 1
    assert result.iloc[0]["indicator_value"] == 55.5


# ---------------------------------------------------------------------------
# Cross-source aggregate
# ---------------------------------------------------------------------------
def test_build_visit_disease_summary_counts_cases_per_month_region_disease():
    facilities = pd.DataFrame({
        "facility_id": ["FAC001"], "facility_name": ["City Hospital"],
        "region": ["Addis Ababa"], "facility_type": ["Hospital"],
        "ownership": ["Government"],
    })
    cases = pd.DataFrame({
        "case_id": ["C1", "C2"], "patient_id": ["P1", "P2"],
        "disease_name": ["Malaria", "Malaria"],
        "facility_id": ["FAC001", "FAC001"],
        "diagnosis_date": pd.to_datetime(["2024-01-05", "2024-01-20"]),
        "severity": ["Mild", "Severe"],
    })
    visits = pd.DataFrame()  # not used by this function's current logic
    summary = build_visit_disease_summary(visits, cases, facilities)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["case_month"] == "2024-01"
    assert row["region"] == "Addis Ababa"
    assert row["disease_name"] == "Malaria"
    assert row["case_count"] == 2


# ---------------------------------------------------------------------------
# Basic validation: after full transform, key columns should never be null
# where the schema requires NOT NULL (mirrors sql/schema.sql constraints).
# ---------------------------------------------------------------------------
def test_transformed_patient_visits_has_no_null_required_fields():
    df = pd.DataFrame({
        "visit_id": ["V1"], "patient_id": ["P1"], "facility_code": ["FAC001"],
        "region_name": ["AA"], "visit_date": ["2024-01-01"], "age": ["30"],
        "gender": ["M"],
    })
    result = clean_patient_visits(df)
    assert result["facility_code"].notna().all()
    assert result["visit_date"].notna().all()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
