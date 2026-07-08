"""Turn raw FHIR resources into rows for our simplified schema.

Every function here is pure: a plain dict goes in and a plain dict comes out.
No network, no database. That makes the tricky FHIR-navigation logic easy to
unit-test in isolation, which is exactly where the bugs tend to hide."""

from typing import Optional, Tuple


# --- Patient ---------------------------------------------------------------

def _pick_name(fhir_patient: dict) -> Tuple[Optional[str], Optional[str]]:
    """Patient.name is a list of names with different uses. Prefer the one
    marked 'official'; otherwise just take the first we're given."""
    names = fhir_patient.get("name") or []
    if not names:
        return None, None

    chosen = next((n for n in names if n.get("use") == "official"), names[0])
    family = chosen.get("family")
    given_parts = chosen.get("given") or []
    given = " ".join(given_parts) if given_parts else None
    return given, family


def _pick_medical_record_number(fhir_patient: dict) -> Optional[str]:
    """Patient.identifier is a list. Prefer one whose type is 'MR' (medical
    record), otherwise fall back to the first identifier that has a value."""
    identifiers = fhir_patient.get("identifier") or []

    for identifier in identifiers:
        codings = (identifier.get("type") or {}).get("coding") or []
        if any(coding.get("code") == "MR" for coding in codings) and identifier.get("value"):
            return identifier["value"]

    for identifier in identifiers:
        if identifier.get("value"):
            return identifier["value"]

    return None


def fhir_patient_to_internal(fhir_patient: dict) -> dict:
    given_name, family_name = _pick_name(fhir_patient)
    return {
        "patient_id": fhir_patient["id"],
        "medical_record_number": _pick_medical_record_number(fhir_patient),
        "given_name": given_name,
        "family_name": family_name,
        "gender": fhir_patient.get("gender"),
        "birth_date": fhir_patient.get("birthDate"),
    }


# --- Observation -----------------------------------------------------------

def _pick_code(fhir_observation: dict) -> Tuple[Optional[str], Optional[str]]:
    """Observation.code is a CodeableConcept with one or more codings. Prefer
    a LOINC coding; fall back to any coding, then to the free-text label."""
    code_concept = fhir_observation.get("code") or {}
    codings = code_concept.get("coding") or []

    loinc = next(
        (c for c in codings if "loinc" in (c.get("system") or "").lower()), None
    )
    chosen = loinc or (codings[0] if codings else {})

    code = chosen.get("code")
    label = chosen.get("display") or code_concept.get("text")
    return code, label


def _extract_value(fhir_observation: dict) -> dict:
    """FHIR spreads the result across many value[x] fields. Flatten whichever
    one is present into our typed shape (type + number + unit + text)."""
    if "valueQuantity" in fhir_observation:
        quantity = fhir_observation["valueQuantity"]
        return {
            "value_type": "quantity",
            "value_number": quantity.get("value"),
            "value_unit": quantity.get("unit") or quantity.get("code"),
            "value_text": None,
        }

    if "valueInteger" in fhir_observation:
        return {
            "value_type": "quantity",
            "value_number": float(fhir_observation["valueInteger"]),
            "value_unit": None,
            "value_text": None,
        }

    if "valueString" in fhir_observation:
        return {
            "value_type": "text",
            "value_number": None,
            "value_unit": None,
            "value_text": fhir_observation["valueString"],
        }

    if "valueCodeableConcept" in fhir_observation:
        concept = fhir_observation["valueCodeableConcept"]
        codings = concept.get("coding") or []
        label = concept.get("text") or (codings[0].get("display") if codings else None)
        return {
            "value_type": "coded",
            "value_number": None,
            "value_unit": None,
            "value_text": label,
        }

    if "valueBoolean" in fhir_observation:
        return {
            "value_type": "text",
            "value_number": None,
            "value_unit": None,
            "value_text": "true" if fhir_observation["valueBoolean"] else "false",
        }

    # Some observations (e.g. blood pressure) carry only components and no
    # top-level value. We record that honestly rather than inventing a value.
    return {"value_type": "none", "value_number": None, "value_unit": None, "value_text": None}


def _extract_patient_id(fhir_observation: dict) -> Optional[str]:
    """Observation.subject is a reference like 'Patient/123'. Pull out the id."""
    reference = (fhir_observation.get("subject") or {}).get("reference") or ""
    if reference.startswith("Patient/"):
        return reference.split("/", 1)[1]
    return None


def _extract_effective_time(fhir_observation: dict) -> Optional[str]:
    """The time can be a single dateTime or a period; take whichever exists."""
    if "effectiveDateTime" in fhir_observation:
        return fhir_observation["effectiveDateTime"]
    period = fhir_observation.get("effectivePeriod") or {}
    return period.get("start")


def fhir_observation_to_internal(fhir_observation: dict) -> dict:
    code, label = _pick_code(fhir_observation)
    row = {
        "observation_id": fhir_observation["id"],
        "patient_id": _extract_patient_id(fhir_observation),
        "code": code,
        "code_label": label,
        "status": fhir_observation.get("status"),
        "effective_time": _extract_effective_time(fhir_observation),
    }
    row.update(_extract_value(fhir_observation))
    return row
