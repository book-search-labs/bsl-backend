# LLM Gateway Service (LLMGW)

Centralized LLM access with API keys, rate limits, retries, audit logging, and cost control.

## Endpoints
- `GET /health`
- `GET /ready`
- `POST /v1/generate`

## Config (env)
- `LLM_GATEWAY_KEYS` (comma-separated api keys; empty = allow all)
- `LLM_RATE_LIMIT_RPM` (default 60)
- `LLM_COST_BUDGET_USD` (default 5.0)
- `LLM_COST_PER_1K` (default 0.002)
- `LLM_AUDIT_LOG_PATH` (default `var/llm_gateway/audit.log`)
- `LLM_DEFAULT_MODEL` (default `toy-rag-v1`)

## Run
```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```
