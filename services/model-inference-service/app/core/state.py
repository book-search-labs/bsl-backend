from app.core.batcher import DynamicBatcher
from app.core.limits import RequestLimiter
from app.core.model_manager import ModelManager
from app.core.embed_manager import EmbedModelManager
from app.core.registry import ModelRegistry
from app.core.settings import SETTINGS

registry = ModelRegistry(SETTINGS.registry_path, SETTINGS.registry_refresh_ms)
model_manager = ModelManager(registry)
request_limiter = RequestLimiter(SETTINGS.max_concurrency, SETTINGS.max_queue)
embed_manager = EmbedModelManager()

batcher = None
if SETTINGS.batch_enabled:
    batcher = DynamicBatcher(model_manager, SETTINGS.batch_window_ms, SETTINGS.batch_max_pairs)
