from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="LLM Gateway", version="v1")
app.include_router(router)
