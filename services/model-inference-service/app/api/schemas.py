from typing import List, Optional
from pydantic import BaseModel, Field


class ScoreOptions(BaseModel):
    timeout_ms: Optional[int] = Field(default=None, alias="timeout_ms")
    return_debug: Optional[bool] = Field(default=None, alias="return_debug")


class ScoreFeatures(BaseModel):
    lex_rank: Optional[int] = Field(default=None, alias="lex_rank")
    vec_rank: Optional[int] = Field(default=None, alias="vec_rank")
    rrf_score: Optional[float] = Field(default=None, alias="rrf_score")
    issued_year: Optional[int] = Field(default=None, alias="issued_year")
    volume: Optional[int] = None
    edition_labels: Optional[List[str]] = Field(default=None, alias="edition_labels")


class ScorePair(BaseModel):
    pair_id: Optional[str] = Field(default=None, alias="pair_id")
    query: str
    doc: Optional[str] = None
    doc_id: Optional[str] = Field(default=None, alias="doc_id")
    features: Optional[ScoreFeatures] = None


class ScoreRequest(BaseModel):
    version: str
    trace_id: str
    request_id: str
    model: Optional[str] = None
    task: Optional[str] = None
    pairs: List[ScorePair]
    options: Optional[ScoreOptions] = None


class ScoreResponse(BaseModel):
    version: str
    trace_id: str
    request_id: str
    model: str
    took_ms: int = Field(default=0, alias="took_ms")
    scores: List[float]
    debug: Optional[dict] = None


class EmbedRequest(BaseModel):
    model: Optional[str] = None
    texts: List[str] = Field(min_items=1)
    normalize: Optional[bool] = True
    trace_id: Optional[str] = None
    request_id: Optional[str] = None


class EmbedResponse(BaseModel):
    version: str
    trace_id: str
    request_id: str
    model: str
    dim: int
    vectors: List[List[float]]


class SpellRequest(BaseModel):
    version: str
    trace_id: str
    request_id: str
    text: str = Field(min_length=1)
    locale: Optional[str] = None
    model: Optional[str] = None


class SpellResponse(BaseModel):
    version: str
    trace_id: str
    request_id: str
    model: str
    corrected: str
    confidence: float
    latency_ms: int = Field(default=0, alias="latency_ms")


class ModelInfo(BaseModel):
    id: str
    task: str
    status: str
    backend: Optional[str] = None
    active: Optional[bool] = None
    canary: Optional[bool] = None
    canary_weight: Optional[float] = Field(default=None, alias="canary_weight")
    artifact_uri: Optional[str] = Field(default=None, alias="artifact_uri")
    loaded: Optional[bool] = None
    updated_at: Optional[str] = Field(default=None, alias="updated_at")


class ModelsResponse(BaseModel):
    version: str
    trace_id: str
    request_id: str
    models: List[ModelInfo]


class ReadyResponse(BaseModel):
    status: str
    models_ready: int = Field(default=0, alias="models_ready")
    models_total: int = Field(default=0, alias="models_total")
