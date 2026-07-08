"""A small HTTP client for the source FHIR server.

It does only what this exercise needs: fetch a page of patients, and fetch a
patient's observations. The one non-trivial part is retry/backoff, because the
public sandbox is shared and will occasionally return a 500 or time out through
no fault of ours. We retry those transient failures a few times with growing
delays, and give up cleanly with a clear error if the server stays down."""

import logging
import time

import requests

from app import config

logger = logging.getLogger(__name__)

# Statuses worth retrying: rate-limiting and transient server errors.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class FHIRClientError(Exception):
    """Raised when a request keeps failing after we exhaust our retries."""


class FHIRClient:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or config.FHIR_BASE_URL).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/fhir+json"})

    def _get(self, resource_path: str, params: dict) -> dict:
        """GET a FHIR endpoint, retrying transient failures with backoff."""
        url = f"{self.base_url}/{resource_path}"
        last_error = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
                )
                if response.status_code in RETRYABLE_STATUSES:
                    raise requests.HTTPError(
                        f"transient HTTP {response.status_code}"
                    )
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as error:
                last_error = error
                wait_seconds = config.BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "GET %s failed (attempt %d/%d): %s. Retrying in %.1fs",
                    resource_path, attempt, config.MAX_RETRIES, error, wait_seconds,
                )
                if attempt < config.MAX_RETRIES:
                    time.sleep(wait_seconds)

        raise FHIRClientError(
            f"Gave up on {resource_path} after {config.MAX_RETRIES} attempts: {last_error}"
        )

    @staticmethod
    def _resources_in(bundle: dict) -> list:
        """Pull the resource objects out of a FHIR search Bundle."""
        return [
            entry["resource"]
            for entry in (bundle.get("entry") or [])
            if "resource" in entry
        ]

    def fetch_patients(self, limit: int) -> list:
        """Fetch a single, bounded page of Patient resources."""
        bundle = self._get("Patient", {"_count": limit})
        return [
            resource
            for resource in self._resources_in(bundle)
            if resource.get("resourceType") == "Patient"
        ]

    def fetch_observations_for_patient(self, patient_id: str, limit: int) -> list:
        """Fetch a bounded set of Observations belonging to one patient."""
        bundle = self._get("Observation", {"patient": patient_id, "_count": limit})
        return [
            resource
            for resource in self._resources_in(bundle)
            if resource.get("resourceType") == "Observation"
        ]
