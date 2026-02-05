# BSL — Local 8B LLM behind LLMGW (Minimal-change Ticket Set)

> Target shape: **BFF → QS → LLM Gateway(LLMGW) → Local LLM (OpenAI-compatible HTTP)**  
> Principle: keep **QS↔LLMGW contract** stable as much as possible; swap **LLMGW provider** from `toy` to `openai_compat`.

## Recommended execution order (why)
1. **Run Local LLM server first** → you get a real endpoint to integrate/test against.
2. **LLMGW provider adapter** → the only “real” code change needed; QS/BFF stay mostly untouched.
3. **Streaming pass-through** (optional but high ROI) → improves UX; keeps infra stable.
4. **Hardening (timeouts/observability)** → production-like safety.

---

## B-0260 — Local LLM Runtime: Docker Compose profile (Ollama or vLLM) + model bootstrap

### Goal
Bring up a **local OpenAI-compatible LLM endpoint** that LLMGW can call.

### Scope
- Add `docker-compose.local-llm.yml` (or profile in existing compose):
  - Option A (simplest): **Ollama** container + OpenAI-compatible API enabled
  - Option B (higher throughput): **vLLM OpenAI-compatible server**
- Choose one default model (8B-ish):
  - `llama3.1:8b-instruct` OR `qwen2.5:7b-instruct`
- Add `make local-llm-up`, `make local-llm-down`, `make local-llm-health`

### Deliverables
- Compose + README snippet:
  - base URL (example): `http://localhost:11434/v1` (Ollama) OR `http://localhost:8000/v1` (vLLM)
  - model name string to pass downstream
- Health check:
  - `GET /v1/models` returns chosen model in list

### Acceptance Criteria
- [ ] `curl <BASE_URL>/v1/models` succeeds locally
- [ ] Sample `curl` to `/v1/chat/completions` returns an assistant message

### Notes
- Keep auth optional for local (empty API key allowed), but support an API key env for later.

---

## B-0261 — LLMGW: Provider adapter `openai_compat` (chat.completions) + JSON response shaping

### Goal
Replace the current **toy synthesizer** with a real call to a local OpenAI-compatible server **without changing QS’s call pattern**.

### Scope
- Add provider `OPENAI_COMPAT` (name can be `openai_compat`) to LLMGW.
- Implement request mapping:
  - LLMGW `/v1/generate` (existing) → provider `/v1/chat/completions`
- Implement response mapping back to LLMGW shape (existing response contract).
- Keep `citations_required` behavior:
  - If QS expects structured `{answer, citations}`: enforce via prompt + post-parse validation.
  - On parse failure: return `status=fallback` with reason code (do **not** crash).

### New/updated env vars (LLMGW)
- `LLM_PROVIDER=openai_compat`
- `LLM_BASE_URL=http://localhost:11434/v1`  (example)
- `LLM_API_KEY=` (optional for local)
- `LLM_MODEL=llama3.1:8b-instruct` (or your chosen model id)
- `LLM_TIMEOUT_MS=15000`
- `LLM_MAX_TOKENS=512`
- `LLM_TEMPERATURE=0.2`

### Endpoint behavior
- **Non-stream**:
  - LLMGW calls `POST {LLM_BASE_URL}/chat/completions` with `stream=false`
- **Stream (optional, see B-0262)**:
  - LLMGW calls same endpoint with `stream=true` and relays SSE.

### Acceptance Criteria
- [ ] With `LLM_PROVIDER=openai_compat`, QS chat returns a non-toy response (real model output).
- [ ] If model returns malformed JSON / missing citations, LLMGW returns a controlled fallback (reason code recorded).
- [ ] Timeouts return a controlled error/fallback (no thread leak, no hanging).

### Test Plan
- Unit: provider client builds payload correctly (model/messages/max_tokens)
- Integration: mock OpenAI-compat server (wiremock) for:
  - success
  - timeout
  - malformed JSON
- Smoke: local E2E BFF→QS→LLMGW→Local LLM

---

## B-0262 — True streaming (minimal): LLMGW SSE relay + QS pass-through (BFF stays proxy)

> If your repo already has real SSE end-to-end, reduce this to a “verify & harden” ticket.

### Goal
When `options.stream=true`, return **real incremental tokens** end-to-end:
**Local LLM stream → LLMGW stream → QS stream → BFF stream**

### Scope
- LLMGW:
  - Support `stream=true` and relay provider SSE events
  - Convert provider deltas into your internal SSE event model (or pass through if already aligned)
- QS:
  - If it calls LLMGW with stream, it should **not buffer** the full response
  - Forward events as they arrive
- BFF:
  - Ensure it does **not** “split tokens” after the fact (proxy-only behavior)

### Env vars
- `LLM_STREAM_ENABLED=true` (optional; or infer from request)
- `QS_CHAT_STREAM_ENABLED=true` (optional)

### Acceptance Criteria
- [ ] First token latency improves (visible in logs/metrics)
- [ ] Streaming endpoint doesn’t allocate the whole response in memory
- [ ] Non-stream behavior unchanged

### Test Plan
- Local: `curl -N` /chat?stream=true and confirm multiple SSE events
- Failure: provider disconnect mid-stream → client gets `error` + `done` safely

---

## B-0263 — Prompt & schema hardening for RAG citations (keep current “citations_required” guarantee)

### Goal
Make “RAG + citations” stable with a real LLM:
- Always produce **machine-parseable** citations referencing retrieved chunks.

### Scope
- Define/confirm a single response JSON schema for chat generation:
  - `{ "answer": string, "citations": [{ "chunk_id": string, "title"?: string, "url"?: string }] }`
- Add robust parser:
  - tolerate extra text before/after JSON (strip, then parse)
  - validate `chunk_id` is from retrieved set
- Fallback policy:
  - missing/invalid citations → `status=fallback` + reason code

### Acceptance Criteria
- [ ] 95%+ of responses parse cleanly in local tests (seed prompts)
- [ ] Invalid citations never leak to users (always replaced by fallback)

---

## B-0264 — Local Dev UX: one-command E2E + smoke tests

### Goal
Make it easy to run the full chain locally and prove it works.

### Scope
- `make up` brings up: MySQL/OpenSearch + services + local LLM
- Add `scripts/smoke_chat.sh`:
  - non-stream chat
  - stream chat
  - “no chunks” fallback scenario
- Update README: required ports, env examples

### Acceptance Criteria
- [ ] Fresh clone → set env → `make up` → smoke script passes
- [ ] Logs show `trace_id/request_id` across BFF→QS→LLMGW

---

## Minimal configuration example (copy/paste)

### LLMGW (.env.local)
```bash
LLM_PROVIDER=openai_compat
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=
LLM_MODEL=llama3.1:8b-instruct
LLM_TIMEOUT_MS=15000
LLM_MAX_TOKENS=512
LLM_TEMPERATURE=0.2
```

### QS (.env.local)
```bash
QS_LLM_URL=http://llm-gateway-service:8000   # or localhost if running outside docker
QS_LLM_MODEL=llama3.1:8b-instruct            # optional: pass-through label
```

---

## What stays unchanged (by design)
- Client/BFF still calls **QS /chat**
- QS still calls **LLMGW /v1/generate**
- Only LLMGW “provider” swaps from **toy** → **openai_compat**
