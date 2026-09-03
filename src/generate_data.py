"""
generate_data.py
-----------------
Generates small, SYNTHETIC (fake, not real) healthcare-style datasets that
imitate what you'd realistically get from 4 different systems that were
never designed to talk to each other.

Why synthetic and "messy on purpose"?
  - Using real patient data would raise privacy/ethics problems, so every
    record here is randomly generated and does not describe a real person.
  - Real multi-source integration projects are messy: different naming
    conventions, different date formats, missing values, and duplicates.
    We recreate that messiness deliberately so the transform step in this
    project has real work to do, instead of just copying clean data around.

Run:
    python src/generate_data.py

Output (written to data/raw/):
    facilities.csv
    patient_visits.csv
    disease_cases.csv
    monthly_indicators.csv
"""

import random
import csv
from datetime import date, timedelta
from pathlib import Path

random.seed(42)  # fixed seed -> reproducible dataset every time this is run

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Reference lists.
# Regions are deliberately spelled inconsistently ACROSS files (e.g.
# "Addis Ababa" vs "addis_ababa" vs "AA") to force the transform stage to
# standardize them, which is a very common real-world data-cleaning task.
# ---------------------------------------------------------------------------
REGIONS_CANONICAL = [
    "Addis Ababa", "Oromia", "Amhara", "Tigray", "SNNPR", "Somali",
]

REGION_ALIASES = {
    "Addis Ababa": ["Addis Ababa", "addis ababa", "AA", "Addis"],
    "Oromia": ["Oromia", "oromia", "ORO"],
    "Amhara": ["Amhara", "amhara", "AMH"],
    "Tigray": ["Tigray", "tigray", "TIG"],
    "SNNPR": ["SNNPR", "snnpr", "SNNP"],
    "Somali": ["Somali", "somali", "SOM"],
}

FACILITY_TYPES = ["Hospital", "Health Center", "Clinic"]
OWNERSHIPS = ["Government", "Private", "NGO"]
DISEASES = ["Malaria", "Malnutrition", "Diarrheal Disease", "Pneumonia",
            "Hypertension", "Diabetes", "Tuberculosis"]
SEVERITIES = ["Mild", "Moderate", "Severe", None]  # None -> missing value on purpose
GENDERS = ["M", "F", "Male", "Female", None]  # inconsistent + missing on purpose


def _random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def _messy_date_str(d: date) -> str:
    """Return the date in one of several formats, to mimic different source
    systems that each store dates their own way."""
    fmt = random.choice(["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%d %b %Y"])
    return d.strftime(fmt)


# ---------------------------------------------------------------------------
# 1) facilities.csv  — the "master list" of health facilities
# ---------------------------------------------------------------------------
def generate_facilities(n=18):
    rows = []
    for i in range(1, n + 1):
        region = random.choice(REGIONS_CANONICAL)
        rows.append({
            "facility_id": f"FAC{i:03d}",
            "facility_name": f"{region.split()[0]} {random.choice(FACILITY_TYPES)} {i}",
            "region": random.choice(REGION_ALIASES[region]),  # messy alias on purpose
            "facility_type": random.choice(FACILITY_TYPES),
            "ownership": random.choice(OWNERSHIPS),
        })
    # inject one exact duplicate row (common real-world data issue)
    rows.append(rows[3].copy())
    path = RAW_DIR / "facilities.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")
    return rows


# ---------------------------------------------------------------------------
# 2) patient_visits.csv — visit-level log, one row per patient visit
#    NOTE: uses "facility_code" (not "facility_id") and "region_name" (not
#    "region") to simulate a *different* system with different column names.
# ---------------------------------------------------------------------------
def generate_patient_visits(facility_rows, n=500):
    rows = []
    start, end = date(2024, 1, 1), date(2025, 12, 31)
    for i in range(1, n + 1):
        fac = random.choice(facility_rows)
        visit_date = _random_date(start, end)
        age = random.choice([random.randint(0, 95), None, -3])  # None/-3 = bad data on purpose
        rows.append({
            "visit_id": f"V{i:05d}",
            "patient_id": f"P{random.randint(1, 350):05d}",  # patients can have >1 visit
            "facility_code": fac["facility_id"],
            "region_name": fac["region"],
            "visit_date": _messy_date_str(visit_date),
            "age": age,
            "gender": random.choice(GENDERS),
        })
    # duplicate a few visit rows exactly (system re-sent the same record)
    for _ in range(4):
        rows.append(random.choice(rows).copy())
    path = RAW_DIR / "patient_visits.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")
    return rows


# ---------------------------------------------------------------------------
# 3) disease_cases.csv — diagnosis log. Refers to facilities by NAME instead
#    of ID (yet another common real-world mismatch) and uses yet another
#    date format.
# ---------------------------------------------------------------------------
def generate_disease_cases(facility_rows, n=300):
    rows = []
    start, end = date(2024, 1, 1), date(2025, 12, 31)
    for i in range(1, n + 1):
        fac = random.choice(facility_rows)
        rows.append({
            "case_id": f"C{i:05d}",
            "patient_id": f"P{random.randint(1, 350):05d}",
            "disease_name": random.choice(DISEASES),
            "facility": fac["facility_name"],  # joined by NAME, not ID
            "diagnosis_date": _messy_date_str(_random_date(start, end)),
            "severity": random.choice(SEVERITIES),
        })
    path = RAW_DIR / "disease_cases.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")
    return rows


# ---------------------------------------------------------------------------
# 4) monthly_indicators.csv — pre-aggregated indicators reported per region
#    per month, as many national health information systems (e.g. DHIS2)
#    actually publish data.
# ---------------------------------------------------------------------------
def generate_monthly_indicators():
    rows = []
    indicators = ["Immunization Coverage (%)", "Bed Occupancy Rate (%)",
                  "Antenatal Care Visits"]
    for year in (2024, 2025):
        for month in range(1, 13):
            for region in REGIONS_CANONICAL:
                for ind in indicators:
                    value = round(random.uniform(40, 99), 1) if "%" in ind \
                        else random.randint(50, 900)
                    rows.append({
                        "month": f"{year}-{month:02d}",
                        "region": random.choice(REGION_ALIASES[region]),
                        "indicator_name": ind,
                        "indicator_value": value,
                    })
    path = RAW_DIR / "monthly_indicators.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")
    return rows


if __name__ == "__main__":
    facilities = generate_facilities()
    generate_patient_visits(facilities)
    generate_disease_cases(facilities)
    generate_monthly_indicators()
    print("\nSynthetic data generation complete.")
