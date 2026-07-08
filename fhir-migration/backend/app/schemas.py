"""Response shapes for the API. These are what the outside world sees, kept
separate from the database models so the two can change independently."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_id: str
    code: Optional[str] = None
    code_label: Optional[str] = None
    status: Optional[str] = None
    effective_time: Optional[str] = None
    value_type: Optional[str] = None
    value_number: Optional[float] = None
    value_unit: Optional[str] = None
    value_text: Optional[str] = None
    value_display: str


class PatientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None


class PatientDetail(PatientSummary):
    medical_record_number: Optional[str] = None
    observations: list[ObservationOut] = []


class MigrationSummary(BaseModel):
    patients_migrated: int
    observations_migrated: int
    patients_failed: int
    observations_failed: int
