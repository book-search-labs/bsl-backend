from fastapi import FastAPI

from app.api.routes import router as api_router
from app.core.settings import SETTINGS
from app.core.state import batcher, embed_manager, model_manager, registry

app = FastAPI(title="model-inference-service")
app.include_router(api_router)


@app.on_event("startup")
async def startup():
    registry.load()
    if batcher is not None:
        await batcher.start()

    if SETTINGS.warmup_enabled:
        spec, model = model_manager.get_model(SETTINGS.default_task, SETTINGS.default_model or None)
        if model is not None:
            pairs = []
            for i in range(max(1, SETTINGS.warmup_pairs)):
                pairs.append({"query": "warmup", "doc_id": f"w{i}", "features": {"rrf_score": 0.1}})
            try:
                import asyncio

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, model.score, pairs)
            except Exception:
                # warmup is best-effort
                pass
        try:
            embed_manager.get_model(SETTINGS.default_embed_model or None).embed(["warmup"], SETTINGS.embed_normalize)
        except Exception:
            pass
