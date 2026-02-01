import os
from dataclasses import dataclass


@dataclass
class Settings:
    env: str = os.getenv("MIS_ENV", "dev")
    max_concurrency: int = int(os.getenv("MIS_MAX_CONCURRENCY", "4"))
    max_queue: int = int(os.getenv("MIS_MAX_QUEUE", "32"))
    timeout_ms: int = int(os.getenv("MIS_TIMEOUT_MS", "200"))
    warmup_enabled: bool = os.getenv("MIS_WARMUP_ENABLED", "true").lower() in {"1", "true", "yes"}
    warmup_pairs: int = int(os.getenv("MIS_WARMUP_PAIRS", "4"))
    batch_enabled: bool = os.getenv("MIS_BATCH_ENABLED", "false").lower() in {"1", "true", "yes"}
    batch_window_ms: int = int(os.getenv("MIS_BATCH_WINDOW_MS", "8"))
    batch_max_pairs: int = int(os.getenv("MIS_BATCH_MAX_PAIRS", "128"))
    registry_path: str = os.getenv("MIS_MODEL_REGISTRY_PATH", "app/config/model_registry.json")
    registry_refresh_ms: int = int(os.getenv("MIS_REGISTRY_REFRESH_MS", "5000"))
    model_dir: str = os.getenv("MIS_MODEL_DIR", "models")
    default_task: str = os.getenv("MIS_DEFAULT_TASK", "rerank")
    default_model: str = os.getenv("MIS_DEFAULT_MODEL", "")
    default_embed_model: str = os.getenv("MIS_DEFAULT_EMBED_MODEL", "")
    embed_backend: str = os.getenv("MIS_EMBED_BACKEND", "toy")
    embed_model_id: str = os.getenv("MIS_EMBED_MODEL_ID", "embed_default")
    embed_model_path: str = os.getenv("MIS_EMBED_MODEL_PATH", "")
    embed_tokenizer_path: str = os.getenv("MIS_EMBED_TOKENIZER_PATH", "")
    embed_output_name: str = os.getenv("MIS_EMBED_OUTPUT_NAME", "")
    embed_dim: int = int(os.getenv("MIS_EMBED_DIM", "768"))
    embed_normalize: bool = os.getenv("MIS_EMBED_NORMALIZE", "true").lower() in {"1", "true", "yes"}
    embed_max_len: int = int(os.getenv("MIS_EMBED_MAX_LEN", "256"))
    embed_batch_size: int = int(os.getenv("MIS_EMBED_BATCH_SIZE", "64"))
    embed_device: str = os.getenv("MIS_EMBED_DEVICE", "cpu")
    onnx_providers: tuple[str, ...] = tuple(
        provider.strip()
        for provider in os.getenv("MIS_ONNX_PROVIDERS", "CPUExecutionProvider").split(",")
        if provider.strip()
    )


SETTINGS = Settings()
