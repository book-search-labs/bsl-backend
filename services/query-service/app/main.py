import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:4173",
]


def parse_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "")
origins = parse_origins(raw_origins)
origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip() or None
if not origins and not origin_regex:
    origins = DEFAULT_CORS_ORIGINS

app = FastAPI(title="query-service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-trace-id", "x-request-id"],
)
app.include_router(api_router)
