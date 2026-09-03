-- schema.sql
-- ----------------------------------------------------------------------
-- Defines the target PostgreSQL tables for the Multi-Source Health Data
-- Integration Pipeline.
--
-- Design notes (why the schema looks like this):
--   * facilities is the "dimension"/master table: one row per facility,
--     with facility_id as its natural primary key.
--   * patient_visits and disease_cases are "fact" tables: many rows, each
--     referencing a facility via foreign key. This mirrors a simple star
--     schema, a standard pattern for analytics-oriented databases.
--   * monthly_indicators is a separate fact table keyed by (month, region,
--     indicator_name) since it comes pre-aggregated from its source system
--     rather than at the individual-record level.
--   * visit_disease_summary is a materialized aggregate table produced by
--     the transform stage (not loaded from a raw source) — it exists so
--     the dashboard can query a small, pre-computed table instead of
--     joining/grouping large fact tables on every page load.
--
-- This file is executed once by src/load.py (idempotently — see the
-- CREATE TABLE IF NOT EXISTS / TRUNCATE pattern in load.py) so re-running
-- the pipeline never fails because "the table already exists".
-- ----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS facilities (
    facility_id     VARCHAR(10) PRIMARY KEY,
    facility_name   VARCHAR(255) NOT NULL,
    region          VARCHAR(100) NOT NULL,
    facility_type   VARCHAR(50),
    ownership       VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS patient_visits (
    visit_id        VARCHAR(10) PRIMARY KEY,
    patient_id      VARCHAR(10) NOT NULL,
    facility_id     VARCHAR(10) REFERENCES facilities(facility_id),
    region          VARCHAR(100),
    visit_date      DATE NOT NULL,
    age             NUMERIC,
    age_group       VARCHAR(10),
    gender          VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS disease_cases (
    case_id         VARCHAR(10) PRIMARY KEY,
    patient_id      VARCHAR(10) NOT NULL,
    disease_name    VARCHAR(100) NOT NULL,
    facility_id     VARCHAR(10) REFERENCES facilities(facility_id),
    diagnosis_date  DATE NOT NULL,
    severity        VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS monthly_indicators (
    month           VARCHAR(7) NOT NULL,   -- 'YYYY-MM'
    region          VARCHAR(100) NOT NULL,
    indicator_name  VARCHAR(100) NOT NULL,
    indicator_value NUMERIC NOT NULL,
    PRIMARY KEY (month, region, indicator_name)
);

CREATE TABLE IF NOT EXISTS visit_disease_summary (
    case_month      VARCHAR(7) NOT NULL,
    region          VARCHAR(100) NOT NULL,
    disease_name    VARCHAR(100) NOT NULL,
    case_count      INTEGER NOT NULL,
    PRIMARY KEY (case_month, region, disease_name)
);

-- Helpful indexes for the query patterns the dashboard uses most often
-- (filtering/grouping by date and region).
CREATE INDEX IF NOT EXISTS idx_visits_date ON patient_visits (visit_date);
CREATE INDEX IF NOT EXISTS idx_visits_region ON patient_visits (region);
CREATE INDEX IF NOT EXISTS idx_cases_date ON disease_cases (diagnosis_date);
CREATE INDEX IF NOT EXISTS idx_cases_disease ON disease_cases (disease_name);
