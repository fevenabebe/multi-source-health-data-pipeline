"""
extract.py
----------
The "E" in ETL.

What this does
    Reads the 4 raw CSV files from data/raw/ into pandas DataFrames and
    returns them as a dictionary. That's it — extraction should be "dumb":
    no cleaning, no business logic, just getting the data out of its
    source system and into a common in-memory format (a DataFrame) so the
    rest of the pipeline can work with it consistently.

Why keep extraction this simple / separate from transform?
    In a real system, each source might be a different technology: a CSV
    export, a REST API, a database table, an Excel file from a partner
    org. If extraction and cleaning are mixed together, swapping one
    source's underlying technology (e.g. CSV -> API) forces you to rewrite
    cleaning logic too. Keeping extract() dumb means you can change *how*
    you fetch data without touching *what you do with it*.

Input
    Nothing (reads from disk), or a `raw_dir` path override.
Output
    dict[str, pandas.DataFrame], one entry per source file, e.g.:
        {
            "facilities": DataFrame,
            "patient_visits": DataFrame,
            "disease_cases": DataFrame,
            "monthly_indicators": DataFrame,
        }
"""

from pathlib import Path
import pandas as pd

DEFAULT_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

SOURCE_FILES = {
    "facilities": "facilities.csv",
    "patient_visits": "patient_visits.csv",
    "disease_cases": "disease_cases.csv",
    "monthly_indicators": "monthly_indicators.csv",
}


def extract(raw_dir: Path = DEFAULT_RAW_DIR) -> dict[str, pd.DataFrame]:
    """Read every raw source CSV into a DataFrame.

    Parameters
    ----------
    raw_dir : Path
        Directory containing the raw CSV files. Defaults to data/raw/.

    Returns
    -------
    dict[str, pd.DataFrame]
        Keyed by logical source name (not filename), e.g. "facilities".
    """
    raw_dir = Path(raw_dir)
    dataframes = {}
    for name, filename in SOURCE_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Expected raw data file not found: {path}. "
                f"Run `python src/generate_data.py` first."
            )
        # dtype=str keeps everything as text at this stage. Type conversion
        # (turning "30" into an integer, "2024-01-05" into a date) is a
        # TRANSFORM concern, not an extraction concern — extraction should
        # not silently guess types and risk misreading messy source data.
        dataframes[name] = pd.read_csv(path, dtype=str)
        print(f"[extract] {name}: {len(dataframes[name])} rows from {path.name}")
    return dataframes


if __name__ == "__main__":
    data = extract()
    for name, df in data.items():
        print(f"\n--- {name} ---")
        print(df.head(3))
