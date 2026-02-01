# File: tasks/backlog/B-0316-mis-real-spell-model-serving.md

# B-0316 — MIS: Real Spell Correction Model Serving (/v1/spell)

## Goal
Replace QS spell no-op provider with a real spell correction model served by MIS.
MIS should host a production-ready spell model (baseline: T5-based Korean typo correction) and expose `/v1/spell`
so QS can call it via HTTP provider.

## Background / Current State
- QS spell is provider-based (`QS_SPELL_PROVIDER`) and defaults to off/no-op.
- HTTP provider exists and can call an external endpoint (default `/v1/spell`), then applies guardrails.
- Repository currently has no bundled T5 weights nor serving implementation for spell.

## Scope
1) Add MIS endpoint: `POST /v1/spell`
2) Load and run a real spell model:
  - Baseline option A (recommended): ONNX Runtime (CPU) for stability and simple deploy
  - Option B: HuggingFace Transformers + Torch (slower cold start, heavier deps)
3) Provide a stable request/response contract (SSOT JSON schema in `contracts/`)
4) Add guardrails in MIS response metadata (confidence, latency_ms) so QS can decide accept/reject
5) Provide local/dev fallback:
  - If model artifacts are missing, return 503 with clear error OR fallback to toy/mock (configurable)

## Non-goals
- Training the model from scratch (we only integrate an existing checkpoint)
- Full quality tuning / dataset curation (separate ticket)
- LLM rewrite / RAG rewrite (separate QS tickets)

## API
### Request (proposed)
{
"version": "v1",
"request_id": "...",
"trace_id": "...",
"text": "정약    용  자서전 01권",
"locale": "ko-KR",
"model": "t5-typo-ko-v1"
}

### Response (proposed)
{
"version": "v1",
"request_id": "...",
"trace_id": "...",
"model": "t5-typo-ko-v1",
"corrected": "정약용 자서전 1권",
"confidence": 0.78,
"latency_ms": 34
}

## Config (env)
- MIS_SPELL_ENABLE=1
- MIS_SPELL_MODEL_ID=t5-typo-ko-v1
- MIS_SPELL_BACKEND=onnx|torch
- MIS_SPELL_MODEL_PATH=/models/spell/t5-typo-ko-v1/
- MIS_SPELL_MAX_LEN=64
- MIS_SPELL_TIMEOUT_MS=80
- MIS_SPELL_BATCH_SIZE=16 (optional)

## DoD
- `/v1/spell` works end-to-end in local compose/dev (even if using a small baseline model)
- Has timeout + concurrency guard (reuse existing RequestLimiter pattern)
- Returns deterministic schema-valid response
- Unit tests:
  - happy path (mock model backend ok)
  - missing model artifact path -> 503 or configured fallback
  - input validation (empty, too long)
- Contracts + examples added and validated in CI

## Files to Change (expected)
- `services/model-inference-service/app/api/routes.py`
- `services/model-inference-service/app/api/schemas.py`
- `services/model-inference-service/app/core/settings.py`
- `services/model-inference-service/app/core/models.py` (add SpellModel interface + impl)
- `contracts/mis-spell-request.schema.json`
- `contracts/mis-spell-response.schema.json`
- `contracts/examples/mis-spell-*.sample.json`
- tests under `services/model-inference-service/tests/`

## Commands
- `cd services/model-inference-service && pytest -q`
- (if present) `./scripts/validate_schemas.sh`

## Codex Prompt
Implement MIS /v1/spell with a real spell model backend (prefer ONNX Runtime) and SSOT contracts.
Add env-configurable model loading, timeouts, concurrency guardrails, tests, and examples.
Keep the change isolated and backwards compatible with existing MIS endpoints.
