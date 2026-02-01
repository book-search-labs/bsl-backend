# File: tasks/backlog/B-0317-qs-enable-http-spell-provider-to-mis.md

# B-0317 — QS: Enable HTTP spell provider (call MIS /v1/spell) + wiring + metrics

## Goal
Make QS spell correction actually run by wiring the existing HTTP provider to MIS `/v1/spell`,
including proper request/response parsing, caching, metrics, and safe degrade behavior.

## Background / Current State
- QS has provider-based spell path (off/mock/rule/http).
- Default is off; mock/rule are placeholders.
- HTTP provider can call an external endpoint but must be validated against real MIS schema.

## Scope
1) Set the default recommended configuration docs for enabling spell via MIS:
  - QS_SPELL_PROVIDER=http
  - QS_SPELL_URL=http://model-inference-service:xxxx
  - QS_SPELL_PATH=/v1/spell
2) Ensure request body matches MIS contract
3) Parse response fields robustly:
  - accept corrected from `corrected` (primary)
  - optionally accept `q_spell` or `text` for backward compatibility
4) Apply existing QS guardrails (length/edit distance/numeric/ISBN/volume preservation)
5) Cache spell result within enhance cache payload
6) Add metrics + debug fields
7) Degrade cleanly on timeout/errors (keep original + reason_codes)

## Non-goals
- Implement T5 inside QS (MIS is the serving layer)
- Rewrite/RAG rewrite

## DoD
- When strategy requires spell, QS actually calls MIS and returns spell.q_spell != input for common typos
- On MIS failure/timeout, QS returns 200 with original text and reason_codes including mis_spell_error/timeout
- Tests:
  - HTTP provider path mocked
  - Guardrail reject case
  - Cache hit path
- Docs updated for env variables

## Files to Change
- `services/query-service/app/core/spell.py` (or where provider lives)
- `services/query-service/app/core/enhance.py`
- `services/query-service/app/api/routes.py`
- tests under `services/query-service/tests/`
- optional: `docs/` or README for env configs

## Commands
- `cd services/query-service && pytest -q`

## Codex Prompt
Wire QS spell HTTP provider to MIS /v1/spell using the new contract.
Add robust parsing, guardrails, caching integration, metrics, and tests.
Ensure graceful degrade on errors.
