# Dockerfile
# ----------------------------------------------------------------------
# One image is used for BOTH the ETL job and the Streamlit dashboard —
# they need the exact same Python dependencies, so building two separate
# images would just duplicate ~500MB of layers for no benefit. Which
# process runs is decided by the `command:` in docker-compose.yml, not by
# anything in this file.
#
# Why python:3.11-slim instead of the full python:3.11 image?
#   The full image bundles a lot of build tooling / docs we don't need at
#   runtime. slim keeps the image small while still having a working
#   apt/pip toolchain to install the one native dependency we need
#   (libpq, for psycopg2). This keeps the "lightweight" requirement from
#   the project brief.
# ----------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# libpq-dev + gcc are required to build psycopg2 from source on some
# platforms; on most platforms psycopg2-binary avoids needing these, but
# installing them keeps the build robust across host architectures
# (e.g. Apple Silicon vs Intel).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No CMD here on purpose: docker-compose.yml sets a different `command:`
# for the "pipeline" service (run once and exit) vs the "dashboard"
# service (run continuously). Keeping the image generic makes it usable
# for both without a second Dockerfile.
