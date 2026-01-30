import logging
import os
import threading
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import Settings
from app.db import Database, utc_now
from app.opensearch import OpenSearchClient
from app.reindex import ReindexRunner
from app.schemas import HealthResponse, ReindexJobCreateRequest, ReindexJobResponse

settings = Settings.from_env()
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("index-writer")

db = Database(settings)
client = OpenSearchClient(settings)
runner = ReindexRunner(settings, db, client)

app = FastAPI(title="index-writer-service")

stop_event = threading.Event()


def request_context(request: Request) -> Dict[str, str]:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
    return {"request_id": request_id, "trace_id": trace_id}


def error_payload(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    ctx = request_context(request)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message},
            "trace_id": ctx["trace_id"],
            "request_id": ctx["request_id"],
        },
    )


def map_job(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "reindex_job_id": row["reindex_job_id"],
        "logical_name": row["logical_name"],
        "from_physical": row.get("from_physical"),
        "to_physical": row.get("to_physical"),
        "status": row.get("status"),
        "params": row.get("params_json"),
        "progress": row.get("progress_json"),
        "error": row.get("error_json"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "paused_at": row.get("paused_at"),
    }


def worker_loop() -> None:
    logger.info("Index writer worker started")
    while not stop_event.is_set():
        try:
            job = db.claim_next_job()
            if job:
                logger.info("Claimed job_id=%s status=%s", job["reindex_job_id"], job["status"])
                try:
                    runner.run_job(job)
                except Exception:
                    # Error already recorded; continue to next job
                    pass
            else:
                time.sleep(settings.job_poll_interval_sec)
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)
            time.sleep(settings.job_poll_interval_sec)


@app.on_event("startup")
def on_startup() -> None:
    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()
    app.state.worker_thread = thread


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_event.set()


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    code = str(exc.detail or "http_error")
    message = str(exc.detail or "http_error")
    return error_payload(request, code, message, exc.status_code)


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_payload(request, "invalid_request", "invalid_request", 400)


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return error_payload(request, "internal_error", "internal_error", 500)


@app.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    ctx = request_context(request)
    return HealthResponse(status="ok", trace_id=ctx["trace_id"], request_id=ctx["request_id"])


@app.post("/internal/index/reindex-jobs", response_model=ReindexJobResponse)
async def create_reindex_job(request: Request, payload: ReindexJobCreateRequest) -> ReindexJobResponse:
    ctx = request_context(request)
    params = payload.params.model_dump(exclude_none=True) if payload.params else {}
    from_physical = db.get_alias_physical(settings.doc_read_alias)
    job = db.insert_job(payload.logical_name, params, from_physical)
    return ReindexJobResponse(version="v1", trace_id=ctx["trace_id"], request_id=ctx["request_id"], job=map_job(job))


@app.get("/internal/index/reindex-jobs/{job_id}", response_model=ReindexJobResponse)
async def get_reindex_job(job_id: int, request: Request) -> ReindexJobResponse:
    ctx = request_context(request)
    job = db.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    return ReindexJobResponse(version="v1", trace_id=ctx["trace_id"], request_id=ctx["request_id"], job=map_job(job))


@app.post("/internal/index/reindex-jobs/{job_id}/pause", response_model=ReindexJobResponse)
async def pause_reindex_job(job_id: int, request: Request) -> ReindexJobResponse:
    ctx = request_context(request)
    job = db.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    db.update_job_status(job_id, "PAUSED", progress=job.get("progress_json"), paused_at=utc_now())
    job = db.fetch_job(job_id)
    return ReindexJobResponse(version="v1", trace_id=ctx["trace_id"], request_id=ctx["request_id"], job=map_job(job))


@app.post("/internal/index/reindex-jobs/{job_id}/resume", response_model=ReindexJobResponse)
async def resume_reindex_job(job_id: int, request: Request) -> ReindexJobResponse:
    ctx = request_context(request)
    job = db.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    db.update_job_status(job_id, "RESUME", progress=job.get("progress_json"))
    job = db.fetch_job(job_id)
    return ReindexJobResponse(version="v1", trace_id=ctx["trace_id"], request_id=ctx["request_id"], job=map_job(job))


@app.post("/internal/index/reindex-jobs/{job_id}/retry", response_model=ReindexJobResponse)
async def retry_reindex_job(job_id: int, request: Request) -> ReindexJobResponse:
    ctx = request_context(request)
    job = db.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    db.update_job_status(job_id, "RETRY", progress=job.get("progress_json"))
    job = db.fetch_job(job_id)
    return ReindexJobResponse(version="v1", trace_id=ctx["trace_id"], request_id=ctx["request_id"], job=map_job(job))
