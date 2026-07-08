"""Runs the migration end to end: fetch from FHIR, transform, persist locally.

Two design choices worth calling out:

- Idempotent. Patients and observations are upserted on their FHIR id, so
  running this twice updates rows in place instead of duplicating them. That
  also makes recovery simple: if a run dies partway, just run it again.

- Fault-tolerant per record. One patient or observation that fails to map is
  logged and skipped, rather than blowing up the whole run. We commit after
  each patient so progress is checkpointed as we go.
"""

import logging

from sqlalchemy.orm import Session

from app import config
from app.database import Base, SessionLocal, engine
from app.fhir_client import FHIRClient, FHIRClientError
from app.models import Observation, Patient
from app.transform import fhir_observation_to_internal, fhir_patient_to_internal

logger = logging.getLogger(__name__)


def _upsert(session: Session, model, primary_key_field: str, row: dict) -> None:
    """Insert the row, or update the existing record with the same key."""
    key = row[primary_key_field]
    existing = session.get(model, key)
    if existing is None:
        session.add(model(**row))
    else:
        for field, value in row.items():
            setattr(existing, field, value)


def run_migration(
    patient_limit: int = None,
    observations_per_patient: int = None,
    client: FHIRClient = None,
    session: Session = None,
) -> dict:
    """Run one migration pass and return a small summary of what happened."""
    patient_limit = patient_limit or config.PATIENT_FETCH_LIMIT
    observations_per_patient = observations_per_patient or config.OBSERVATIONS_PER_PATIENT_LIMIT

    Base.metadata.create_all(bind=engine)

    client = client or FHIRClient()
    owns_session = session is None
    session = session or SessionLocal()

    summary = {
        "patients_migrated": 0,
        "observations_migrated": 0,
        "patients_failed": 0,
        "observations_failed": 0,
    }

    try:
        fhir_patients = client.fetch_patients(patient_limit)
        logger.info("Fetched %d patients from the source", len(fhir_patients))

        for fhir_patient in fhir_patients:
            patient_id = fhir_patient.get("id")

            try:
                _upsert(session, Patient, "patient_id", fhir_patient_to_internal(fhir_patient))
                summary["patients_migrated"] += 1
            except Exception as error:  # noqa: BLE001 - keep going on a bad record
                summary["patients_failed"] += 1
                logger.error("Failed to migrate patient %s: %s", patient_id, error)
                continue

            try:
                fhir_observations = client.fetch_observations_for_patient(
                    patient_id, observations_per_patient
                )
            except FHIRClientError as error:
                # Couldn't get this patient's observations, but the patient
                # themselves migrated fine. Log it and move on.
                logger.error("Could not fetch observations for patient %s: %s", patient_id, error)
                fhir_observations = []

            for fhir_observation in fhir_observations:
                try:
                    row = fhir_observation_to_internal(fhir_observation)
                    # Fall back to the patient we asked about if the reference
                    # is missing, so the row still links correctly.
                    if row["patient_id"] is None:
                        row["patient_id"] = patient_id
                    _upsert(session, Observation, "observation_id", row)
                    summary["observations_migrated"] += 1
                except Exception as error:  # noqa: BLE001
                    summary["observations_failed"] += 1
                    logger.error(
                        "Failed to migrate observation %s: %s",
                        fhir_observation.get("id"), error,
                    )

            session.commit()  # checkpoint progress after each patient

        logger.info("Migration finished: %s", summary)
        return summary
    finally:
        if owns_session:
            session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_migration()
    print("\nMigration summary:")
    for name, count in result.items():
        print(f"  {name}: {count}")
