# FHIR Migration Service

A small but working slice of the migration described in [`PLAN.md`](./PLAN.md).
It pulls `Patient` and `Observation` resources from the public HAPI FHIR R4
sandbox, maps them into a simplified internal schema, stores them in SQLite, and
serves them through a small REST API. A React frontend lists the migrated
patients and shows one patient's observations when you click them.

The source is the public synthetic sandbox at `https://hapi.fhir.org/baseR4`.
No real patient data or PHI is involved.

## How it fits together

```
HAPI FHIR sandbox  ──fetch──▶  transform  ──upsert──▶  SQLite  ──▶  FastAPI  ──▶  React UI
    (source)                 (FHIR → ours)            (local)     (read API)     (browser)
```

- **Backend** (Python / FastAPI): the FHIR client, the transform, the SQLite
  store, and the read API.
- **Frontend** (React / Vite): a two-pane viewer over the API.

## Prerequisites

- Python 3.10+ (developed on 3.12)
- Node.js 18+ (developed on 22)

## Backend: setup and run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**1. Run the migration** to pull data from the sandbox into a local SQLite file
(`migrated_data.db`):

```bash
python -m app.migrate
```

You'll see a summary like `patients_migrated: 20, observations_migrated: 137, ...`.
The run is safe to repeat: records are upserted on their FHIR id, so running it
again updates rows in place rather than creating duplicates.

**2. Start the API:**

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive API docs are then at `http://localhost:8000/docs`.

### API endpoints

| Method | Path                    | Description                                  |
|--------|-------------------------|----------------------------------------------|
| GET    | `/health`               | Liveness check                               |
| GET    | `/patients`             | List migrated patients (summary fields)      |
| GET    | `/patients/{id}`        | One patient with their observations, or 404  |
| POST   | `/migrate`              | Run a migration pass (used by the UI button) |

### Run the tests

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

The tests cover the transform (the tricky FHIR-navigation logic and value
flattening), the API endpoints including the 404 path, and the retry/backoff
behaviour of the FHIR client. They use captured sample payloads and a throwaway
in-memory database, so they need no network.

## Frontend: setup and run

Start the backend first, then:

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (default `http://localhost:5173`). If your data isn't
there yet, click **Run migration**, then click any patient to see their
observations. If the backend runs somewhere other than `http://localhost:8000`,
set `VITE_API_BASE_URL` before `npm run dev`.

## Design decisions

- **Why FastAPI + SQLite.** FastAPI gives clean endpoints and correct status
  codes with little ceremony, and SQLite means the whole thing runs from this
  README with no database server to install.
- **Simplified internal schema.** We keep the fields that matter (name, gender,
  birth date, a medical record number, and for observations a code, value,
  unit, status, and time) and drop the rest of FHIR's depth. See `app/models.py`.
- **Handling FHIR's awkward parts.** `Patient.name` and `Patient.identifier` are
  lists, so we pick the `official` name and the `MR` (medical record)
  identifier rather than blindly taking the first. `Observation.value[x]` is
  polymorphic, so we flatten it into a small typed shape: a `value_type`
  discriminator plus a number, unit, and text. See `app/transform.py`.
- **Idempotent migration.** The FHIR resource id is the primary key, and writes
  are upserts, so re-running is safe and recovery is just "run it again."
- **Failure handling.** Transient sandbox errors (429/5xx, timeouts) are retried
  with exponential backoff before giving up with a clear error. One bad record
  is logged and skipped instead of failing the whole run, and progress is
  committed after each patient.

## Scope

Intentionally left out, to keep the core clean (these are covered as the
production design in `PLAN.md`, not built here):

- Authentication / authorization
- Deployment / hosting
- Full-volume pagination and delta/real-time sync the migration pulls a
  bounded batch (configurable via `PATIENT_FETCH_LIMIT`)
- Visual styling polish

## A note on responsible data handling

This exercise uses only the public **synthetic** sandbox, so there is no PHI
here. The code is still written to behave as if there were: it logs resource
**ids and error types, never patient content**, so nothing sensitive would leak
into logs. The real-world PHI story encryption in transit and at rest,
least-privilege access, audit logging, keeping no stray copies of patient data,
and the HIPAA/BAA scope — is laid out in the Safety section of `PLAN.md`.

## Use of AI

In the interest of being upfront, an AI assistant was used on parts of this
project:

- Drafting this README.
- Writing the test cases.
- Autocompleting code and helping scaffold the file/folder structure.

The design choices, the internal schema, the FHIR mapping decisions, and the
overall approach were mine, and I reviewed and ran everything the migration,
the API, and the full test suite — against the live sandbox before submitting.