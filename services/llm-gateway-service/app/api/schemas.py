from typing import List, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str


class RagChunk(BaseModel):
    citation_key: str = Field(alias="citation_key")
    title: Optional[str] = None
    url: Optional[str] = None
    content: str


class RagContext(BaseModel):
    chunks: List[RagChunk] = []


class GenerateRequest(BaseModel):
    version: str = "v1"
    trace_id: Optional[str] = Field(default=None, alias="trace_id")
    request_id: Optional[str] = Field(default=None, alias="request_id")
    model: Optional[str] = None
    messages: List[Message] = []
    max_tokens: Optional[int] = Field(default=None, alias="max_tokens")
    temperature: Optional[float] = None
    context: Optional[RagContext] = None
    citations_required: bool = Field(default=True, alias="citations_required")
    stream: Optional[bool] = None


class GenerateResponse(BaseModel):
    version: str = "v1"
    trace_id: str = Field(alias="trace_id")
    request_id: str = Field(alias="request_id")
    model: str
    content: str
    citations: List[str]
    tokens: int
    cost_usd: float
