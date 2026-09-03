"""
pipeline.py
-----------
Orchestrates the full ETL run: extract() -> transform() -> load().

Why have a separate orchestrator file instead of just running load.py?
    Each of extract.py / transform.py / load.py is written to also be
    runnable and testable on its own (each has a `if __name__ == "__main__"`
    block). pipeline.py is the single entry point that ties the three
    stages together the way they'd actually run in production — this is
    also the file Docker and GitHub Actions call.

Usage:
    python src/pipeline.py
"""

import sys
import time

from extract import extract
from transform import transform
from load import load, get_engine


def run() -> None:
    started = time.time()
    print("=" * 60)
    print("Multi-Source Health Data Integration Pipeline")
    print("=" * 60)

    print("\n[1/3] EXTRACT")
    raw = extract()

    print("\n[2/3] TRANSFORM")
    cleaned = transform(raw)

    print("\n[3/3] LOAD")
    engine = get_engine()
    load(cleaned, engine)

    elapsed = time.time() - started
    print(f"\nPipeline finished successfully in {elapsed:.1f}s.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # surface a clear failure in CI/Docker logs
        print(f"\nPipeline FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
