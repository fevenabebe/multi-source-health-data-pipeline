-- analytics.sql
-- ----------------------------------------------------------------------
-- Realistic reporting queries against the loaded, cleaned data.
-- These demonstrate: joins, aggregation (GROUP BY), filtering, window-style
-- share-of-total calculations, and reusable views.
--
-- These are the SAME queries the Streamlit dashboard (dashboard/app.py)
-- runs — this file documents them independently so they can be reviewed,
-- reused in a SQL client (psql, DBeaver, etc.), or discussed in an
-- interview without needing to read the Python.
-- ----------------------------------------------------------------------

-- 1. Total facilities
SELECT COUNT(*) AS total_facilities FROM facilities;

-- 2. Total patient visits
SELECT COUNT(*) AS total_visits FROM patient_visits;

-- 3. Total disease cases
SELECT COUNT(*) AS total_cases FROM disease_cases;

-- 4. Visits by region
SELECT region, COUNT(*) AS visit_count
FROM patient_visits
GROUP BY region
ORDER BY visit_count DESC;

-- 5. Cases by disease, with percentage share of all cases
SELECT
    disease_name,
    COUNT(*) AS case_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
FROM disease_cases
GROUP BY disease_name
ORDER BY case_count DESC;

-- 6. Monthly patient visit trend
SELECT
    TO_CHAR(visit_date, 'YYYY-MM') AS visit_month,
    COUNT(*) AS visit_count
FROM patient_visits
GROUP BY visit_month
ORDER BY visit_month;

-- 7. Monthly disease-case trend (uses the pre-aggregated summary table)
SELECT case_month, SUM(case_count) AS total_cases
FROM visit_disease_summary
GROUP BY case_month
ORDER BY case_month;

-- 8. Top 5 facilities by number of visits (JOIN + GROUP BY + LIMIT)
SELECT
    f.facility_name,
    f.region,
    COUNT(v.visit_id) AS visit_count
FROM facilities f
JOIN patient_visits v ON v.facility_id = f.facility_id
GROUP BY f.facility_name, f.region
ORDER BY visit_count DESC
LIMIT 5;

-- 9. Cases by region and disease (two-dimensional breakdown)
SELECT region, disease_name, SUM(case_count) AS case_count
FROM visit_disease_summary
GROUP BY region, disease_name
ORDER BY region, case_count DESC;

-- 10. Age-group breakdown of visits (filters out unknown age groups)
SELECT age_group, COUNT(*) AS visit_count
FROM patient_visits
WHERE age_group IS NOT NULL
GROUP BY age_group
ORDER BY age_group;

-- 11. Latest reported value of each monthly indicator, per region
SELECT DISTINCT ON (region, indicator_name)
    region, indicator_name, month, indicator_value
FROM monthly_indicators
ORDER BY region, indicator_name, month DESC;

-- ----------------------------------------------------------------------
-- VIEWS
-- Views wrap the queries above so the dashboard (or any SQL client) can
-- just `SELECT * FROM view_name` instead of repeating the full query.
-- ----------------------------------------------------------------------

CREATE OR REPLACE VIEW view_visits_by_region AS
SELECT region, COUNT(*) AS visit_count
FROM patient_visits
GROUP BY region;

CREATE OR REPLACE VIEW view_cases_by_disease AS
SELECT
    disease_name,
    COUNT(*) AS case_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
FROM disease_cases
GROUP BY disease_name;

CREATE OR REPLACE VIEW view_monthly_visit_trend AS
SELECT TO_CHAR(visit_date, 'YYYY-MM') AS visit_month, COUNT(*) AS visit_count
FROM patient_visits
GROUP BY visit_month;

CREATE OR REPLACE VIEW view_top_facilities AS
SELECT
    f.facility_name,
    f.region,
    COUNT(v.visit_id) AS visit_count
FROM facilities f
JOIN patient_visits v ON v.facility_id = f.facility_id
GROUP BY f.facility_name, f.region
ORDER BY visit_count DESC;
