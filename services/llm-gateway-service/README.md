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
- `LLM_AUDIT_DB_ENABLED` (default `false`; when true, writes to MySQL `llm_audit_log`)
- `LLM_AUDIT_DB_HOST` (default `127.0.0.1`)
- `LLM_AUDIT_DB_PORT` (default `3306`)
- `LLM_AUDIT_DB_NAME` (default `bsl`)
- `LLM_AUDIT_DB_USER` (default `bsl`)
- `LLM_AUDIT_DB_PASSWORD` (default `bsl`)
- `LLM_AUDIT_DB_CONNECT_TIMEOUT_MS` (default `200`)
- `LLM_AUDIT_DB_SERVICE_NAME` (default `llm-gateway`)
- `LLM_REDIS_URL` (optional; enables shared budget tracking)
- `LLM_BUDGET_WINDOW_SEC` (default `86400`, applies only when Redis is enabled)
- `LLM_BUDGET_KEY` (default `llm:budget:global`)
- `LLM_PROVIDER` (`toy` or `openai_compat`, default `toy`)
- `LLM_BASE_URL` (default `http://localhost:11434/v1`)
- `LLM_API_KEY` (optional)
- `LLM_MODEL` (preferred; overrides default model)
- `LLM_DEFAULT_MODEL` (fallback, default `toy-rag-v1`)
- `LLM_TIMEOUT_MS` (default `15000`)
- `LLM_MAX_TOKENS` (default `512`)
- `LLM_TEMPERATURE` (default `0.2`)

## Run
```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```
