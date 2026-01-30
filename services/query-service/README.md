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
```

## Test
```bash
python3 -m pytest
```
