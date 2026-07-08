// Where the backend lives. Override with VITE_API_BASE_URL if it's elsewhere.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return response.json();
}

export function fetchPatients() {
  return request("/patients");
}

export function fetchPatient(patientId) {
  return request(`/patients/${patientId}`);
}

export function runMigration() {
  return request("/migrate", { method: "POST" });
}
