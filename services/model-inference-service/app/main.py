from fastapi import FastAPI

from app.api.routes import router as api_router

app = FastAPI(title="model-inference-service")
app.include_router(api_router)
