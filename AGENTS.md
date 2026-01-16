# AGENTS.md — Rules for Codex/Agent Work

This repository is developed with a **context-engineering** approach.
Agents must treat repository files as the **single source of truth (SSOT)** and follow the rules below.

---

## 0) Golden Rules (Must Follow)

1. **SSOT order**
  - **contracts/** (schemas, examples) is the highest SSOT for inter-service data.
  - **data-model/** + **db/** are SSOT for source domain data (catalog).
  - **infra/opensearch/** is SSOT for derived search index (mapping/analyzers).
  - **docs/** explains rationale (ADR) and usage (runbooks), but must not contradict SSOT.

2. **Change order**
  - If behavior or payload changes: **contracts → code → tests → docs**
  - If only implementation changes: **code → tests → docs** (contracts unchanged)

3. **One PR = One task**
  - Keep PRs small and focused.
  - Avoid unrelated refactors.

4. **No silent spec changes**
  - Do not modify `contracts/**` unless the task explicitly says so.
  - If spec changes are needed, propose a separate PR.

5. **Always run checks**
  - Run `./scripts/test.sh` (or the project test entrypoint) before finishing.
  - If `RUN_E2E=1` is available, run it when the task requires end-to-end validation.

---

## 1) Working Style

- Prefer **minimal, composable changes**.
- Do not invent new fields or endpoints not documented in:
  - `docs/API_SURFACE.md`
  - `contracts/*.schema.json`
- If you must add an endpoint, update **API surface docs** and add a **contract + example**.

---

## 2) Repository Structure (What to Read First)

Agents should read the following at the start of each task:

- `Plans.md` — current milestone and scope
- `docs/ARCHITECTURE.md` — service boundaries and flow
- `docs/API_SURFACE.md` — endpoints and payload references
- `contracts/` — request/response schemas + examples
- `infra/opensearch/` — index mappings and versioning rules (for search work)
- `data-model/` and `db/` — catalog source-of-truth model (for ingestion/indexing work)

---

## 3) Contracts (Inter-service SSOT)

- All service-to-service payloads MUST conform to JSON Schemas in `contracts/`.
- Add/Update `contracts/examples/*.sample.json` whenever contracts change.
- Ensure `scripts/validate_contracts.py` (if present) passes.

**Schema versioning**
- Use `version: "v1"` style for payload version.
- If breaking changes occur, create `v2` schemas and keep `v1` for compatibility.

---

## 4) OpenSearch Index (Derived SSOT)

- Mappings/analyzers live under `infra/opensearch/`.
- Do **not** edit an existing “current version” mapping in-place if it’s breaking:
  - Create `books_v2.mapping.json` and follow alias/blue-green rules in `INDEX_VERSIONING.md`.

---

## 5) Logging & Trace Propagation

- Every request/response should carry:
  - `trace_id`, `request_id`
- Services must preserve these IDs across internal calls.
- Logs should include `trace_id`, `request_id`, and `service` name.

---

## 6) Error Handling (If present)

- If `contracts/error.schema.json` exists, all services must return that shape for errors.
- Do not leak secrets/PII in error messages or logs.

---

## 7) Testing & Validation

Minimum required before completing a task:
- `./scripts/test.sh` passes (or equivalent)
- Unit/integration test added for new behavior when feasible
- If task touches contracts:
  - examples updated
  - schema validation passes

---

## 8) What NOT to Do

- Do not change `contracts/**` unless explicitly asked.
- Do not perform large refactors unrelated to the task.
- Do not introduce new dependencies without strong justification.
- Do not commit generated secrets or private data dumps (e.g., raw NLK 10GB).

---

## 9) Task Completion Checklist

Before declaring done, provide:
- Summary of changes
- Files changed list
- How to run tests
- Any follow-up TODOs (separately)

---

## 10) Communication Format (Preferred)

When responding in PR/task outputs, use:
- ✅ Done: ...
- 🔍 Tested: ...
- 📄 Docs updated: ...
- ⚠️ Notes / Follow-ups: ...
