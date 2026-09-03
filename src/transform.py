"""
transform.py
------------
The "T" in ETL — and where most of the real engineering work happens.

Each function below does ONE cleaning/transformation job and is documented
with what it does and why it's necessary. transform() composes them into
the full pipeline for each dataset, then joins everything into a single
"analytics-ready" table plus a couple of aggregate summaries.

Design principle: small, single-purpose, testable functions.
    Instead of one giant "clean everything" function, each transformation
    step is its own function. This makes each step independently testable
    (see tests/test_pipeline.py), easier to reason about, and easier to
    reuse. This is the same principle behind Unix pipes: small tools, each
    doing one job well, composed together.

Input
    dict[str, pd.DataFrame] — the raw dictionary returned by extract()
Output
    dict[str, pd.DataFrame] — cleaned, standardized tables ready to load
    into PostgreSQL:
        {
            "facilities": ...,
            "patient_visits": ...,
            "disease_cases": ...,
            "monthly_indicators": ...,
            "visit_disease_summary": ...,   # a calculated aggregate table
        }
"""

from __future__ import annotations
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Reference data used for standardization.
# In a bigger project this "region lookup" would itself live in a database
# table or config file; here a small dict is enough and keeps the project
# easy to read end-to-end.
# ---------------------------------------------------------------------------
REGION_LOOKUP = {
    "addis ababa": "Addis Ababa", "aa": "Addis Ababa", "addis": "Addis Ababa",
    "oromia": "Oromia", "oro": "Oromia",
    "amhara": "Amhara", "amh": "Amhara",
    "tigray": "Tigray", "tig": "Tigray",
    "snnpr": "SNNPR", "snnp": "SNNPR",
    "somali": "Somali", "som": "Somali",
}

GENDER_LOOKUP = {
    "m": "Male", "male": "Male",
    "f": "Female", "female": "Female",
}


def standardize_region(series: pd.Series) -> pd.Series:
    """Map inconsistent region spellings ('AA', 'addis ababa', 'Addis') onto
    one canonical name ('Addis Ababa').

    Why: the 4 source files each spell region names differently. If we
    don't standardize this, a GROUP BY region in SQL later would treat
    'Addis Ababa' and 'addis ababa' as two different regions, which would
    silently corrupt every regional statistic in the dashboard.
    """
    return (
        series.astype(str).str.strip().str.lower()
        .map(REGION_LOOKUP)
        .fillna(series.astype(str).str.strip())  # keep original if unknown
    )


def standardize_gender(series: pd.Series) -> pd.Series:
    """Map 'M'/'Male'/'m' etc. onto one of 'Male', 'Female', or 'Unknown'.

    Why: free-text/coded fields captured by different systems (or by
    different clinic staff) are rarely consistent. Standardizing avoids
    fragmenting a simple two-category breakdown into five categories.
    """
    mapped = series.astype(str).str.strip().str.lower().map(GENDER_LOOKUP)
    return mapped.fillna("Unknown")


def parse_messy_date(series: pd.Series) -> pd.Series:
    """Parse a column that mixes multiple date formats
    ('2024-01-05', '05/01/2024', '01-05-2024', '5 Jan 2024') into proper
    pandas Timestamps, using several format attempts.

    Why: dates are one of the most common integration failure points.
    Downstream SQL time-series queries (monthly trends) are only correct
    if every date is a real, comparable date value — not a string.
    Unparseable values become NaT (pandas' "missing date") rather than
    crashing the pipeline, and are counted so data quality is visible
    instead of hidden.
    """
    s = series.astype(str).str.strip()
    result = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%d %b %Y"]
    remaining = s.copy()
    for fmt in formats:
        mask = result.isna() & remaining.notna()
        parsed = pd.to_datetime(remaining[mask], format=fmt, errors="coerce")
        result.loc[mask] = parsed
    n_failed = result.isna().sum()
    if n_failed:
        print(f"[transform] warning: {n_failed} dates could not be parsed")
    return result


def clean_age(series: pd.Series) -> pd.Series:
    """Convert age to a numeric column and null out impossible values.

    Why: source systems sometimes store negative ages or blanks due to
    data-entry error. Rather than silently keeping bad values (which would
    skew an average-age indicator) or silently dropping the whole row
    (which loses the rest of a valid record), we null out just the invalid
    age and keep the row.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where((numeric >= 0) & (numeric <= 120))


def make_age_group(age_series: pd.Series) -> pd.Series:
    """Calculated field: bucket numeric age into standard age groups.

    Why: dashboards and public-health reporting almost always need age
    BANDS (0-4, 5-17, ...) rather than exact ages, both for readability
    and to avoid displaying near-identifying detail for small facilities.
    """
    bins = [-1, 4, 17, 39, 59, 200]
    labels = ["0-4", "5-17", "18-39", "40-59", "60+"]
    return pd.cut(age_series, bins=bins, labels=labels)


# ---------------------------------------------------------------------------
# Per-source cleaning pipelines
# ---------------------------------------------------------------------------
def clean_facilities(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]  # standardize column names
    df["region"] = standardize_region(df["region"])
    before = len(df)
    df = df.drop_duplicates(subset=["facility_id"])  # exact-duplicate rows injected in generator
    if len(df) < before:
        print(f"[transform] facilities: dropped {before - len(df)} duplicate rows")
    df = df.dropna(subset=["facility_id"])  # a facility record with no ID is unusable -> validation rule
    return df.reset_index(drop=True)


def clean_patient_visits(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.drop_duplicates()  # exact duplicate visit records
    df["region_name"] = standardize_region(df["region_name"])
    df["visit_date"] = parse_messy_date(df["visit_date"])
    df["age"] = clean_age(df["age"])
    df["age_group"] = make_age_group(df["age"])
    df["gender"] = standardize_gender(df["gender"])
    # Validation rule: a visit with no facility reference or no date is not
    # analytically usable (we can't attribute it to a place or a time), so
    # rather than guessing we exclude it and report how many were dropped —
    # keeping the transform's data-quality impact visible instead of silent.
    before = len(df)
    df = df.dropna(subset=["facility_code", "visit_date"])
    if len(df) < before:
        print(f"[transform] patient_visits: dropped {before - len(df)} rows missing facility/date")
    return df.reset_index(drop=True)


def clean_disease_cases(df: pd.DataFrame, facilities: pd.DataFrame) -> pd.DataFrame:
    """disease_cases.csv links to a facility by NAME, not ID. We resolve
    that to facility_id here so every table in the database can consistently
    join on the same key.

    Why resolve names to IDs instead of keeping names everywhere?
    Names are for humans; IDs are for databases. Facility names can be
    renamed or briefly duplicated ("City Clinic" could exist in two
    regions); a stable ID avoids ambiguous joins later.
    """
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.drop_duplicates()
    df["diagnosis_date"] = parse_messy_date(df["diagnosis_date"])
    df["severity"] = df["severity"].fillna("Unknown")  # missing severity -> explicit "Unknown", not a blank cell

    name_to_id = dict(zip(facilities["facility_name"], facilities["facility_id"]))
    df["facility_id"] = df["facility"].map(name_to_id)
    unmatched = df["facility_id"].isna().sum()
    if unmatched:
        print(f"[transform] disease_cases: {unmatched} rows had a facility name with no match")
    df = df.dropna(subset=["facility_id", "diagnosis_date"])
    return df.reset_index(drop=True)


def clean_monthly_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    df["region"] = standardize_region(df["region"])
    df["indicator_value"] = pd.to_numeric(df["indicator_value"], errors="coerce")
    df = df.dropna(subset=["indicator_value"])
    df = df.drop_duplicates(subset=["month", "region", "indicator_name"])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cross-source join + aggregate ("gold layer")
# ---------------------------------------------------------------------------
def build_visit_disease_summary(visits: pd.DataFrame, cases: pd.DataFrame,
                                 facilities: pd.DataFrame) -> pd.DataFrame:
    """Calculated/aggregated table: monthly disease case counts per facility
    and region, joined against the facilities master list.

    Why build this instead of only loading raw tables?
        This is the classic "star schema" idea in miniature: keep clean
        source-level (fact) tables, but ALSO materialize one pre-aggregated
        summary table so the dashboard doesn't need to re-run an expensive
        multi-table join+group-by every time someone opens it. It also
        demonstrates that the pipeline can *produce* an analytics artifact,
        not just move data around.
    """
    merged = cases.merge(
        facilities[["facility_id", "facility_name", "region"]],
        on="facility_id", how="left",
    )
    merged["case_month"] = merged["diagnosis_date"].dt.to_period("M").astype(str)
    summary = (
        merged.groupby(["case_month", "region", "disease_name"])
        .agg(case_count=("case_id", "count"))
        .reset_index()
        .sort_values(["case_month", "region", "disease_name"])
    )
    return summary


def transform(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Run the full transform stage on every extracted source and return the
    cleaned tables ready for loading into PostgreSQL."""
    facilities = clean_facilities(raw["facilities"])
    visits = clean_patient_visits(raw["patient_visits"])
    cases = clean_disease_cases(raw["disease_cases"], facilities)
    indicators = clean_monthly_indicators(raw["monthly_indicators"])
    summary = build_visit_disease_summary(visits, cases, facilities)

    cleaned = {
        "facilities": facilities,
        "patient_visits": visits,
        "disease_cases": cases,
        "monthly_indicators": indicators,
        "visit_disease_summary": summary,
    }
    for name, df in cleaned.items():
        print(f"[transform] {name}: {len(df)} rows after cleaning")
    return cleaned


if __name__ == "__main__":
    from extract import extract
    raw = extract()
    clean = transform(raw)
    for name, df in clean.items():
        print(f"\n--- {name} ---")
        print(df.head(3))
