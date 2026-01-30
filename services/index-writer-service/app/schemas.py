from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ReindexJobParams(BaseModel):
    index_prefix: Optional[str] = None
    mapping_path: Optional[str] = None
    delete_existing: Optional[bool] = None
    batch_size: Optional[int] = None
    bulk_size: Optional[int] = None
    retry_max: Optional[int] = None
    retry_backoff_sec: Optional[float] = None
    max_failures: Optional[int] = None
    bulk_delay_sec: Optional[float] = None
    refresh_interval_bulk: Optional[str] = None
    refresh_interval_post: Optional[str] = None
    material_kinds: Optional[list[str]] = None


class ReindexJobCreateRequest(BaseModel):
    logical_name: str = Field(default="books_doc")
    params: Optional[ReindexJobParams] = None


class ReindexJobProgress(BaseModel):
    total: Optional[int] = None
    processed: Optional[int] = None
    failed: Optional[int] = None
    retries: Optional[int] = None
    cursor: Optional[Dict[str, Any]] = None
    attempts: Optional[int] = None


class ReindexJobError(BaseModel):
    message: str
    retryable: Optional[bool] = None
    stage: Optional[str] = None
    detail: Optional[Any] = None


class ReindexJob(BaseModel):
    reindex_job_id: int
    logical_name: str
    from_physical: Optional[str] = None
    to_physical: Optional[str] = None
    status: str
    params: Optional[Dict[str, Any]] = None
    progress: Optional[ReindexJobProgress] = None
    error: Optional[ReindexJobError] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None


class ReindexJobResponse(BaseModel):
    version: str = "v1"
    trace_id: str
    request_id: str
    job: ReindexJob


class HealthResponse(BaseModel):
    status: str
    trace_id: str
    request_id: str
