# Index Writer Service

Local-first service to run managed reindex jobs with checkpoint/pause/resume.

## Run (dev)
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a
source .env
set +a
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

## API (internal)
- `POST /internal/index/reindex-jobs`
- `GET /internal/index/reindex-jobs/{id}`
- `POST /internal/index/reindex-jobs/{id}/pause`
- `POST /internal/index/reindex-jobs/{id}/resume`
- `POST /internal/index/reindex-jobs/{id}/retry`

## Notes
- Uses the canonical MySQL schema (`db/migration/V3__catalog_core.sql`).
- Writes progress into `reindex_job.progress_json` and failures into `reindex_error`.
- Blue/green alias swap for `books_doc_read` / `books_doc_write`.
- CORS defaults to local dev origins; override with `CORS_ALLOW_ORIGINS` / `CORS_ALLOW_ORIGIN_REGEX`.
