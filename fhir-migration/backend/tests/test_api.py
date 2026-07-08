"""End-to-end-ish tests for the API and the retry logic.

The API tests use a throwaway SQLite database seeded with a couple of rows, so
they exercise the real endpoints, real ORM, and real serialization without
touching the network. The retry test checks that a transient server error is
retried and then succeeds."""

from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config
from app.database import Base, get_db_session
from app.fhir_client import FHIRClient, FHIRClientError
from app.main import app
from app.models import Observation, Patient


@pytest.fixture()
def client():
    """A TestClient wired to a fresh in-memory database seeded with sample data."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection so :memory: persists
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()
    session.add(Patient(patient_id="p1", given_name="Peter", family_name="Chalmers", gender="male"))
    session.add(Observation(
        observation_id="o1", patient_id="p1", code="8867-4", code_label="Heart rate",
        status="final", value_type="quantity", value_number=72, value_unit="beats/minute",
    ))
    session.commit()
    session.close()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_patients(client):
    response = client.get("/patients")
    assert response.status_code == 200
    patients = response.json()
    assert len(patients) == 1
    assert patients[0]["patient_id"] == "p1"
    assert patients[0]["family_name"] == "Chalmers"


def test_get_patient_includes_observations(client):
    response = client.get("/patients/p1")
    assert response.status_code == 200
    patient = response.json()
    assert patient["patient_id"] == "p1"
    assert len(patient["observations"]) == 1
    observation = patient["observations"][0]
    assert observation["code_label"] == "Heart rate"
    # The computed display string should combine number and unit.
    assert observation["value_display"] == "72.0 beats/minute"


def test_get_missing_patient_returns_404(client):
    response = client.get("/patients/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found"


def test_client_retries_transient_error_then_succeeds(monkeypatch):
    """A 503 should be retried, and a following success should be returned."""
    monkeypatch.setattr("time.sleep", lambda _seconds: None)  # don't actually wait

    failing = MagicMock()
    failing.status_code = 503

    succeeding = MagicMock()
    succeeding.status_code = 200
    succeeding.json.return_value = {"resourceType": "Bundle", "entry": []}
    succeeding.raise_for_status.return_value = None

    fhir_client = FHIRClient(base_url="https://example.test/baseR4")
    # Fail twice, then succeed on the third attempt.
    fhir_client.session.get = MagicMock(side_effect=[failing, failing, succeeding])

    result = fhir_client.fetch_patients(limit=5)

    assert result == []
    assert fhir_client.session.get.call_count == 3


def test_client_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    always_failing = MagicMock()
    always_failing.status_code = 500

    fhir_client = FHIRClient(base_url="https://example.test/baseR4")
    fhir_client.session.get = MagicMock(return_value=always_failing)

    with pytest.raises(FHIRClientError):
        fhir_client.fetch_patients(limit=5)

    assert fhir_client.session.get.call_count == config.MAX_RETRIES
