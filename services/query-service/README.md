# Query Service

## Run
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## Environment
Create a local `.env` (not committed) based on `.env.example`.

```
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:4173
# CORS_ALLOW_ORIGIN_REGEX=
# Optional normalization overrides
# NORMALIZATION_RULES_PATH=../var/normalization/normalization_active.json

# Optional Redis cache / cooldown store
# REDIS_URL=redis://localhost:6379/0

# Cache versions + TTLs (seconds)
# QS_NORM_CACHE_VERSION=v1
# QS_NORM_CACHE_TTL_SEC=3600
# QS_ENH_CACHE_VERSION=v1
# QS_ENH_CACHE_TTL_SEC=900
# QS_ENH_DENY_CACHE_TTL_SEC=120

# Enhance gating budgets
# QS_ENHANCE_WINDOW_SEC=60
# QS_ENHANCE_MAX_PER_WINDOW=60
# QS_ENHANCE_COOLDOWN_SEC=300
# QS_ENHANCE_MAX_PER_QUERY_PER_HOUR=10
# QS_ENHANCE_SCORE_GAP_THRESHOLD=0.05
# QS_ENHANCE_MIN_LATENCY_BUDGET_MS=200

# Rewrite log storage (SQLite path by default)
# QS_REWRITE_DB_PATH=/tmp/qs_rewrite.db

# Spell provider (MIS recommended)
# QS_SPELL_PROVIDER=http
# QS_SPELL_URL=http://localhost:8005
# QS_SPELL_PATH=/v1/spell
# QS_SPELL_MODEL=t5-typo-ko-v1
# QS_SPELL_TIMEOUT_SEC=2.0

# Spell candidate generator + dictionary
# QS_SPELL_CANDIDATE_ENABLE=1
# QS_SPELL_CANDIDATE_MAX=50
# QS_SPELL_CANDIDATE_TOPK=5
# QS_SPELL_CANDIDATE_MIN_SCORE=0.0
# QS_SPELL_EDIT_DISTANCE_MAX=2
# QS_SPELL_KEYBOARD_LOCALE=ko|en|both
# QS_SPELL_CANDIDATE_MODE=hint|prefill
# QS_SPELL_DICT_BACKEND=file
# QS_SPELL_DICT_PATH=data/dict/spell_aliases.jsonl
# QS_SPELL_DICT_REDIS_URL=redis://localhost:6379/1
# QS_SPELL_DICT_REDIS_KEY=qs:spell:dict
# QS_ENHANCE_DEBUG=1

# Chat tool-calling (commerce lookup)
# QS_CHAT_TOOL_ENABLED=1
# QS_COMMERCE_URL=http://localhost:8091/api/v1
# QS_CHAT_TOOL_LOOKUP_TIMEOUT_SEC=2.5
# QS_CHAT_TOOL_LOOKUP_RETRY=1
# QS_CHAT_TOOL_CIRCUIT_FAIL_THRESHOLD=3
# QS_CHAT_TOOL_CIRCUIT_OPEN_SEC=30
# QS_CHAT_POLICY_TOPIC_CACHE_TTL_SEC=300
# QS_CHAT_WORKFLOW_TTL_SEC=900
# QS_CHAT_CONFIRM_TOKEN_TTL_SEC=300
# QS_CHAT_WORKFLOW_MAX_RETRY=1
# QS_CHAT_ACTION_RECEIPT_TTL_SEC=86400

# Chat durable session state store (MySQL, optional)
# QS_CHAT_STATE_DB_ENABLED=false
# QS_CHAT_STATE_DB_HOST=127.0.0.1
# QS_CHAT_STATE_DB_PORT=3306
# QS_CHAT_STATE_DB_NAME=bsl
# QS_CHAT_STATE_DB_USER=bsl
# QS_CHAT_STATE_DB_PASSWORD=bsl
# QS_CHAT_STATE_DB_CONNECT_TIMEOUT_MS=200
# QS_CHAT_LOG_MESSAGE_MODE=masked_raw   # masked_raw | hash_summary

# Chat LLM budget/admission guardrails
# QS_CHAT_MAX_PROVIDER_ATTEMPTS_PER_TURN=2
# QS_CHAT_MAX_PROMPT_TOKENS_PER_TURN=6000
# QS_CHAT_MAX_COMPLETION_TOKENS_PER_TURN=1200

# Chat engine rollout (legacy/agent/canary/shadow)
# QS_CHAT_ENGINE_MODE=agent
# QS_CHAT_ENGINE_CANARY_PERCENT=5
# QS_CHAT_ROLLOUT_AUTO_ROLLBACK_ENABLED=1
# QS_CHAT_ROLLOUT_GATE_WINDOW_SEC=300
# QS_CHAT_ROLLOUT_GATE_MIN_SAMPLES=20
# QS_CHAT_ROLLOUT_GATE_FAIL_RATIO_THRESHOLD=0.2
# QS_CHAT_ROLLOUT_ROLLBACK_COOLDOWN_SEC=60
```

## Endpoints
- `POST /query/prepare` (qc.v1.1 primary contract)
- `POST /query-context` (deprecated alias of `/query/prepare`)
- `POST /query/enhance` (gating + rewrite)
- `GET /internal/qc/rewrite/failures`

## Test
```bash
python3 -m pytest
```
