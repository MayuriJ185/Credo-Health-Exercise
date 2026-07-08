"""The internal REST API over the migrated data.

Endpoints:
  GET  /health                 - liveness check
  GET  /patients               - list migrated patients
  GET  /patients/{patient_id}  - one patient with their observations
  POST /migrate                - run a migration pass (convenience for the demo)
"""

import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db_session
from app.migrate import run_migration
from app.models import Patient
from app.schemas import MigrationSummary, PatientDetail, PatientSummary

logging.basicConfig(level=logging.INFO)

# Make sure the tables exist so the API works even before the first migration.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FHIR Migration Service", version="1.0.0")

# The React dev server runs on a different origin, so let the browser call us.
# Wide-open CORS is fine for a local exercise; you would lock this down in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/patients", response_model=list[PatientSummary])
def list_patients(db: Session = Depends(get_db_session)):
    """List every migrated patient (summary fields only)."""
    return db.query(Patient).order_by(Patient.family_name).all()


@app.get("/patients/{patient_id}", response_model=PatientDetail)
def get_patient(patient_id: str, db: Session = Depends(get_db_session)):
    """Return one patient together with their observations, or 404."""
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@app.post("/migrate", response_model=MigrationSummary)
def trigger_migration(patient_limit: int = None):
    """Run a migration pass on demand. Handy for populating data from the UI."""
    return run_migration(patient_limit=patient_limit)
