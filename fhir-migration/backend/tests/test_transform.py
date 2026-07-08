"""Tests for the FHIR -> internal transform.

These use realistically-shaped FHIR resources and focus on the fiddly bits:
choosing the right name and identifier out of a list, and flattening the
polymorphic Observation.value[x]."""

from app.transform import fhir_observation_to_internal, fhir_patient_to_internal


def test_patient_prefers_official_name_and_mr_identifier():
    fhir_patient = {
        "id": "p1",
        "identifier": [
            {"system": "urn:other", "value": "SSN-999"},
            {
                "type": {"coding": [{"code": "MR"}]},
                "system": "urn:mrns",
                "value": "MRN-123",
            },
        ],
        "name": [
            {"use": "maiden", "family": "Old", "given": ["Nick"]},
            {"use": "official", "family": "Chalmers", "given": ["Peter", "James"]},
        ],
        "gender": "male",
        "birthDate": "1974-12-25",
    }

    result = fhir_patient_to_internal(fhir_patient)

    assert result["patient_id"] == "p1"
    assert result["medical_record_number"] == "MRN-123"  # picked the MR one
    assert result["family_name"] == "Chalmers"           # picked the official name
    assert result["given_name"] == "Peter James"
    assert result["gender"] == "male"
    assert result["birth_date"] == "1974-12-25"


def test_patient_falls_back_when_no_official_name_or_mr_identifier():
    fhir_patient = {
        "id": "p2",
        "identifier": [{"system": "urn:x", "value": "ONLY-ONE"}],
        "name": [{"family": "Solo", "given": ["Han"]}],
    }

    result = fhir_patient_to_internal(fhir_patient)

    assert result["medical_record_number"] == "ONLY-ONE"
    assert result["family_name"] == "Solo"
    assert result["given_name"] == "Han"
    assert result["gender"] is None  # missing fields become None, not errors


def test_observation_quantity_value():
    fhir_observation = {
        "id": "o1",
        "status": "final",
        "subject": {"reference": "Patient/p1"},
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}
            ]
        },
        "effectiveDateTime": "2023-01-01T10:00:00Z",
        "valueQuantity": {"value": 72, "unit": "beats/minute", "code": "/min"},
    }

    result = fhir_observation_to_internal(fhir_observation)

    assert result["observation_id"] == "o1"
    assert result["patient_id"] == "p1"       # parsed out of "Patient/p1"
    assert result["code"] == "8867-4"
    assert result["code_label"] == "Heart rate"
    assert result["status"] == "final"
    assert result["value_type"] == "quantity"
    assert result["value_number"] == 72
    assert result["value_unit"] == "beats/minute"


def test_observation_string_value():
    fhir_observation = {
        "id": "o2",
        "subject": {"reference": "Patient/p1"},
        "code": {"text": "Clinical note"},
        "valueString": "Patient reports mild headache",
    }

    result = fhir_observation_to_internal(fhir_observation)

    assert result["code_label"] == "Clinical note"  # fell back to code.text
    assert result["value_type"] == "text"
    assert result["value_text"] == "Patient reports mild headache"
    assert result["value_number"] is None


def test_observation_coded_value():
    fhir_observation = {
        "id": "o3",
        "subject": {"reference": "Patient/p1"},
        "code": {"coding": [{"system": "http://loinc.org", "code": "x", "display": "Smoking status"}]},
        "valueCodeableConcept": {"text": "Never smoked"},
    }

    result = fhir_observation_to_internal(fhir_observation)

    assert result["value_type"] == "coded"
    assert result["value_text"] == "Never smoked"


def test_observation_with_no_top_level_value():
    # Blood pressure often carries only components, no value[x] of its own.
    fhir_observation = {
        "id": "o4",
        "subject": {"reference": "Patient/p1"},
        "code": {"coding": [{"code": "85354-9", "display": "Blood pressure"}]},
        "component": [{"code": {"text": "Systolic"}, "valueQuantity": {"value": 120}}],
    }

    result = fhir_observation_to_internal(fhir_observation)

    assert result["value_type"] == "none"
    assert result["value_number"] is None
    assert result["value_text"] is None
