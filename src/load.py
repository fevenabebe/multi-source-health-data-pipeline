"""
load.py
-------
The "L" in ETL.

What this does
    1. Connects to PostgreSQL using SQLAlchemy.
    2. Runs sql/schema.sql to (idempotently) create the tables.
    3. Truncates each table and loads the corresponding cleaned DataFrame
       into it with pandas.DataFrame.to_sql().
    4. Runs sql/analytics.sql to (re)create the reporting views.

Why truncate-then-load instead of append?
    This project's pipeline is designed to be re-run from scratch (e.g. in
    CI, or when you regenerate the synthetic data). Truncate-then-load
    keeps the pipeline idempotent: running it twice produces the same
    result, instead of doubling every row. In a production system you'd
    likely use incremental/upsert loading, but that adds complexity this
    project doesn't need to demonstrate the core ETL/database concepts.

Why SQLAlchemy + psycopg2 instead of a hand-written INSERT loop?
    pandas.to_sql() already knows how to batch-insert a DataFrame
    efficiently and safely (using parameterized queries, so there's no
    SQL-injection risk from data values). Writing our own INSERT loop
    would just re-implement that, with more code and more room for bugs.

Environment variables (all have safe local-dev defaults):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

from __future__ import annotations
import os
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = PROJECT_ROOT / "sql" / "schema.sql"
ANALYTICS_SQL = PROJECT_ROOT / "sql" / "analytics.sql"

# Table load order matters: facilities must load before patient_visits and
# disease_cases because those tables have a FOREIGN KEY back to facilities.
TABLE_ORDER = [
    "facilities",
    "patient_visits",
    "disease_cases",
    "monthly_indicators",
    "visit_disease_summary",
]

# Maps our internal DataFrame column names -> the exact column names the
# database table expects (a couple of source columns were renamed during
# transform, e.g. facility_code -> facility_id).
COLUMN_MAP = {
    "patient_visits": {
        "facility_code": "facility_id",
        "region_name": "region",
    },
}

# The exact column list (and order) each target table expects, matching
# sql/schema.sql. Any other column produced during transform (e.g. the
# original human-readable "facility" name kept in disease_cases for
# traceability/debugging) is dropped here before loading — the raw,
# unresolved value is useful while developing the pipeline, but the
# database should only store the resolved, normalized columns.
TABLE_COLUMNS = {
    "facilities": ["facility_id", "facility_name", "region", "facility_type", "ownership"],
    "patient_visits": ["visit_id", "patient_id", "facility_id", "region", "visit_date",
                        "age", "age_group", "gender"],
    "disease_cases": ["case_id", "patient_id", "disease_name", "facility_id",
                       "diagnosis_date", "severity"],
    "monthly_indicators": ["month", "region", "indicator_name", "indicator_value"],
    "visit_disease_summary": ["case_month", "region", "disease_name", "case_count"],
}


def get_engine() -> Engine:
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "health_pipeline")
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "postgres")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    return create_engine(url)


def _strip_sql_comments(sql_text: str) -> str:
    """Remove '-- ...' line comments before splitting into statements.

    Why this matters: naively splitting the raw file on ';' and then
    dropping any *whole statement* that starts with '--' would also throw
    away real SQL that happens to follow a comment block within the same
    ';'-delimited chunk (e.g. a header comment immediately followed by a
    CREATE TABLE, with no semicolon in between). Stripping comments
    line-by-line first avoids that failure mode.
    """
    lines = []
    for line in sql_text.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _run_sql_file(engine: Engine, path: Path) -> None:
    """Execute a .sql file that may contain multiple ';'-separated
    statements. Comments are stripped first, then the remainder is split
    on ';'. This is a simplification that works fine for this project's
    straightforward DDL/DML files (no semicolons inside string literals or
    function bodies), but would need a real SQL parser for more complex
    scripts."""
    sql_text = _strip_sql_comments(path.read_text())
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def create_schema(engine: Engine) -> None:
    print("[load] creating schema (tables + indexes)...")
    _run_sql_file(engine, SCHEMA_SQL)


def create_views(engine: Engine) -> None:
    print("[load] creating/refreshing analytics views...")
    _run_sql_file(engine, ANALYTICS_SQL)


def load_table(engine: Engine, name: str, df: pd.DataFrame) -> None:
    df = df.rename(columns=COLUMN_MAP.get(name, {}))
    df = df[TABLE_COLUMNS[name]]  # keep/order only the columns the table schema defines
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {name} CASCADE"))
    df.to_sql(name, engine, if_exists="append", index=False, method="multi",
              chunksize=500)
    print(f"[load] {name}: loaded {len(df)} rows")


def load(cleaned: dict[str, pd.DataFrame], engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    create_schema(engine)
    for name in TABLE_ORDER:
        load_table(engine, name, cleaned[name])
    create_views(engine)
    print("[load] done.")


if __name__ == "__main__":
    from extract import extract
    from transform import transform

    raw = extract()
    cleaned = transform(raw)
    load(cleaned)
