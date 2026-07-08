"""All the knobs in one place. Everything can be overridden with an env var,
so the code has sensible defaults but nothing is hard-coded in a way you
can't change at run time."""

import os

# The source FHIR server. Defaults to the public synthetic sandbox.
FHIR_BASE_URL = os.environ.get("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4")

# Where the migrated data lives: a single local SQLite file, no DB server needed.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./migrated_data.db")

# How many patients to pull in one migration run. Kept small on purpose:
# full-volume paging is deliberately out of scope for this exercise.
PATIENT_FETCH_LIMIT = int(os.environ.get("PATIENT_FETCH_LIMIT", "20"))

# How many observations to pull per patient.
OBSERVATIONS_PER_PATIENT_LIMIT = int(os.environ.get("OBSERVATIONS_PER_PATIENT_LIMIT", "50"))

# Retry / backoff settings for talking to the shared (and sometimes flaky) sandbox.
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "4"))
BACKOFF_BASE_SECONDS = float(os.environ.get("BACKOFF_BASE_SECONDS", "0.5"))
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
