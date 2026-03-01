# PG Simulator

로컬에서 결제창 + 웹훅 시나리오를 재현하는 개발용 서비스입니다.

## Run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

## Endpoints

- `GET /health`
- `GET /checkout`
- `GET /simulate`

## Environment

- `PG_SIM_WEBHOOK_SECRET` (default: `dev_local_sim_webhook_secret`)
- `PG_SIM_PROVIDER` (default: `LOCAL_SIM`)
- `PG_SIM_WEBHOOK_TIMEOUT_SEC` (default: `3.0`)
