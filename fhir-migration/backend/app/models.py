"""Our own simplified schema. This is intentionally much flatter than FHIR:
we keep the handful of fields that matter and drop the rest.

Note: the primary key of each table is the *source FHIR id*. That is what
makes the migration idempotent, since we upsert on that key and re-running
never creates duplicates."""

from sqlalchemy import Column, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from app.database import Base


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String, primary_key=True)          # FHIR Patient.id
    medical_record_number = Column(String, nullable=True)  # chosen identifier (MRN)
    given_name = Column(String, nullable=True)
    family_name = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)             # kept as an ISO date string

    observations = relationship(
        "Observation",
        back_populates="patient",
        cascade="all, delete-orphan",
    )


class Observation(Base):
    __tablename__ = "observations"

    observation_id = Column(String, primary_key=True)      # FHIR Observation.id
    patient_id = Column(String, ForeignKey("patients.patient_id"), nullable=False)

    code = Column(String, nullable=True)         # e.g. the LOINC code
    code_label = Column(String, nullable=True)   # human-readable name for the code
    status = Column(String, nullable=True)
    effective_time = Column(String, nullable=True)

    # FHIR's value[x] is polymorphic, so we flatten it into a small typed shape:
    # a discriminator (value_type) plus the number / unit / text that go with it.
    value_type = Column(String, nullable=True)   # "quantity" | "text" | "coded" | "none"
    value_number = Column(Float, nullable=True)
    value_unit = Column(String, nullable=True)
    value_text = Column(String, nullable=True)

    patient = relationship("Patient", back_populates="observations")

    @property
    def value_display(self) -> str:
        """A single readable string for the value, whatever its type."""
        if self.value_type == "quantity" and self.value_number is not None:
            unit = f" {self.value_unit}" if self.value_unit else ""
            return f"{self.value_number}{unit}"
        if self.value_text:
            return self.value_text
        return "\u2014"  # em dash: nothing to show
