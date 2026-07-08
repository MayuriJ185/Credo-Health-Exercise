import { useEffect, useState } from "react";
import { fetchPatient, fetchPatients, runMigration } from "./api";

function fullName(patient) {
  const parts = [patient.given_name, patient.family_name].filter(Boolean);
  return parts.length ? parts.join(" ") : "(no name)";
}

export default function App() {
  const [patients, setPatients] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [listError, setListError] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isMigrating, setIsMigrating] = useState(false);

  async function loadPatients() {
    setIsLoadingList(true);
    setListError(null);
    try {
      setPatients(await fetchPatients());
    } catch (error) {
      setListError(error.message);
    } finally {
      setIsLoadingList(false);
    }
  }

  useEffect(() => {
    loadPatients();
  }, []);

  async function openPatient(patientId) {
    setDetailError(null);
    setSelectedPatient(null);
    try {
      setSelectedPatient(await fetchPatient(patientId));
    } catch (error) {
      setDetailError(error.message);
    }
  }

  async function handleMigrate() {
    setIsMigrating(true);
    try {
      await runMigration();
      await loadPatients();
    } catch (error) {
      setListError(error.message);
    } finally {
      setIsMigrating(false);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Migrated Patients</h1>
        <button onClick={handleMigrate} disabled={isMigrating}>
          {isMigrating ? "Migrating\u2026" : "Run migration"}
        </button>
      </header>

      <div className="layout">
        <section className="panel">
          {isLoadingList && <p className="muted">Loading patients…</p>}
          {listError && <p className="error">Could not load patients: {listError}</p>}

          {!isLoadingList && !listError && patients.length === 0 && (
            <p className="muted">
              No patients yet. Click <strong>Run migration</strong> to pull some
              from the FHIR sandbox.
            </p>
          )}

          <ul className="patient-list">
            {patients.map((patient) => (
              <li key={patient.patient_id}>
                <button
                  className={
                    selectedPatient && selectedPatient.patient_id === patient.patient_id
                      ? "patient-row selected"
                      : "patient-row"
                  }
                  onClick={() => openPatient(patient.patient_id)}
                >
                  <span className="patient-name">{fullName(patient)}</span>
                  <span className="muted">
                    {[patient.gender, patient.birth_date].filter(Boolean).join(" \u00b7 ")}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          {detailError && <p className="error">Could not load patient: {detailError}</p>}

          {!selectedPatient && !detailError && (
            <p className="muted">Select a patient to see their observations.</p>
          )}

          {selectedPatient && (
            <div>
              <h2>{fullName(selectedPatient)}</h2>
              <p className="muted">
                MRN: {selectedPatient.medical_record_number || "\u2014"} &nbsp;|&nbsp;
                ID: {selectedPatient.patient_id}
              </p>

              <h3>Observations ({selectedPatient.observations.length})</h3>
              {selectedPatient.observations.length === 0 ? (
                <p className="muted">This patient has no migrated observations.</p>
              ) : (
                <table className="observations">
                  <thead>
                    <tr>
                      <th>Observation</th>
                      <th>Value</th>
                      <th>Status</th>
                      <th>When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedPatient.observations.map((observation) => (
                      <tr key={observation.observation_id}>
                        <td>{observation.code_label || observation.code || "\u2014"}</td>
                        <td>{observation.value_display}</td>
                        <td>{observation.status || "\u2014"}</td>
                        <td>{observation.effective_time || "\u2014"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
