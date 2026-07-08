# Migration Plan: Legacy FHIR System → New Internal Service

> **Scope note.** This document is the *production* design for the full
> ~50,000-patient migration. The code in this repo is a working slice of it
> against the public sandbox: same shape (fetch → transform → persist → serve),
> but deliberately bounded — no full-volume pagination and no delta sync, since
> those were called out as out of scope. Where the plan and the code differ,
> the plan is the "here's how we'd take this to production" story.

## What I'm assuming

A few things aren't nailed down yet, so I'm stating my assumptions up front. If any of these are wrong, the plan shifts.

- The source is a FHIR R4 API. We're told it's ~50,000 patients, but the real workload is their observations. Assume each patient carries anywhere from a handful to a few hundred observations, which puts us somewhere between one and ten million observation resources. I'm sizing the pipeline around that number, not the patient count.
- The target is a new service we own. It is **not** the system of record yet — the legacy system still is, until we say otherwise.
- I need to confirm whether the source supports the FHIR Bulk Data export (`$export`). The approach branches on the answer, so this is the first thing I'd check.
- **Open question:** is the legacy system still being written to during the migration? I'm assuming we can get a short read-only freeze window. If we can't, we add a delta sync step (see the note at the end), and the job gets meaningfully harder.

## Overall approach

Standard extract → transform → load, but built to be resumable rather than one big all-or-nothing run.

For **extraction**, I'd prefer the bulk export operation if the source supports it — it's designed for exactly this and it's far kinder to the API than pulling millions of resources one page at a time. If bulk export isn't available, the fallback is paginated REST: pull in pages using `_count`, follow the `next` links, and use `_lastUpdated` as a watermark so we can pick up where we left off.

Reliability comes from a few habits, not one clever trick:

- Work in **batches**, and checkpoint after each one. If the job dies at three million records, it resumes at three million, not from zero.
- **Idempotent writes.** Every load is an upsert keyed on a stable source identifier. Re-running the same batch produces the same result — no duplicates. This one property is what makes both retries and rollback cheap.
- A **dead-letter queue** for records that fail to map or load. One malformed record shouldn't kill the whole run; it gets set aside for review while everything else keeps moving.
- **Respect the API.** Bounded concurrency, and exponential backoff on rate-limit (429) and server (5xx) responses. The public sandbox in particular will throw the occasional 500 that has nothing to do with our code — the pipeline should treat that as "wait and retry," not "fail."

For **observability**, I'd emit counters at each stage — extracted, transformed, loaded, failed — plus throughput and the running failure rate, and produce a reconciliation report at the end of the run. Logs carry resource IDs and error types, never patient content. If I can't tell from the logs how far along we are and what's failing, the pipeline isn't done.

## Data mapping

The goal is to flatten rich FHIR resources into a simpler internal shape. Worth saying plainly: **simpler means lossy.** We're choosing to drop detail. So alongside the mapped records, I'd archive the raw FHIR JSON for every resource. If the mapping turns out to be wrong, or we later need a field we dropped, we re-map from the archive instead of going back to a legacy system that may no longer exist.

**Patient** → internal patient:
- `identifier` → our MRN. Note `identifier` is a list; I pick the entry from the correct system, not just the first one.
- `name` → given / family. `name` is also a list, so I take the one where `use = official` and fall back to the first only if there's no official entry.
- `gender`, `birthDate` → straight across.
- Key address and contact details, kept minimal.

**Observation** → internal observation:
- `code` → the clinical concept. I prefer the LOINC coding where there's more than one.
- `status`, `effectiveDateTime` → across as-is.
- `subject` → this points at the source patient. During load I **remap** the source patient ID to our new internal ID, or the link breaks.
- The value is the fiddly part. `Observation.value[x]` is polymorphic — it can be a quantity, a coded concept, plain text, and so on. In the internal model I store a typed value, its unit (UCUM), and a small "value type" flag saying which kind it is, so we don't lose the distinction.

## Validation

A migration isn't done because the job exited cleanly. It's done when we've shown the data is right.

- **Counts.** Compare source vs target counts per resource type. Numbers should reconcile, and any gap should be explainable by the dead-letter queue.
- **Referential integrity.** Every observation in the target must point at a patient that actually exists in the target. No orphans.
- **Sampled field check.** Take a random sample, hash the mapped fields on both sides, and compare. This catches silent mapping bugs that counts alone miss.
- **Sanity checks.** Birth dates aren't in the future, gender values are in the allowed set, numeric observations have units. Cheap to run, catches obvious corruption.
- **Human spot-check.** Someone clinical eyeballs a small sample. Automated checks miss things that a person notices immediately.

## Safety (how the real, PHI-carrying version behaves)

This sandbox holds synthetic data, but the real version handles PHI, and the code should behave as if it always does:

- Everything over TLS in transit, encrypted at rest.
- Credentials live in a secrets manager, never in code or config files.
- **No PHI in logs, metrics, or error messages.** The dead-letter queue stores IDs and the error, not the record body — or if we need the body to debug, it's encrypted.
- Least-privilege service accounts, with an audit trail of who and what accessed the data.
- Any staging store is locked down and deleted after cutover. We don't leave copies of patient data lying around.
- None of this touches production data until the HIPAA/BAA scope and data-residency questions are signed off. That's a gate, not a formality.

## Rollback

Rollback is designed in from the start, not bolted on after something breaks.

- The legacy system stays the source of truth until validation passes. We don't cut over before then, so "roll back" during the migration itself carries no clinical risk.
- Every record we write is tagged with the migration run ID. That makes a run fully deletable — if a batch is bad, we delete by run ID, fix the mapping, and re-run.
- Because writes are idempotent, the recovery story is simply: fix and re-run. Reprocessing can't create duplicates, so there's no cleanup dance.
- At the actual cutover, put the switch behind a feature flag so we can flip back to legacy instantly if something looks wrong in production.

---

*Note on the freeze-window assumption:* if the legacy system can't be frozen and stays live during migration, we add a delta phase — after the bulk load, catch up on everything changed since we started using `_lastUpdated`, and repeat until the gap is small enough to close inside the cutover window. It's doable, but it's extra moving parts, so it's worth confirming early whether we actually need it.
