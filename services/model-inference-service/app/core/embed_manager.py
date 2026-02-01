from typing import Optional

from app.core.models import BaseEmbedModel, OnnxEmbedModel, ToyEmbedModel
from app.core.settings import SETTINGS


class EmbedModelManager:
    def __init__(self) -> None:
        self._model: Optional[BaseEmbedModel] = None
        self._model_id: str = SETTINGS.embed_model_id or "toy_embed_v1"

    def get_model(self, requested_id: Optional[str]) -> BaseEmbedModel:
        if requested_id and self._model_id and requested_id != self._model_id:
            raise RuntimeError("embed_model_not_found")
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def model_id(self) -> str:
        return self._model_id

    def dim(self) -> int:
        return SETTINGS.embed_dim

    def _load_model(self) -> BaseEmbedModel:
        backend = SETTINGS.embed_backend
        if backend == "onnx":
            if not SETTINGS.embed_model_path or not SETTINGS.embed_tokenizer_path:
                raise RuntimeError("embed_model_path_or_tokenizer_missing")
            output_name = SETTINGS.embed_output_name or None
            return OnnxEmbedModel(
                SETTINGS.embed_model_path,
                SETTINGS.embed_tokenizer_path,
                SETTINGS.embed_max_len,
                output_name,
                SETTINGS.onnx_providers,
            )
        if backend == "toy":
            return ToyEmbedModel(SETTINGS.embed_dim)
        raise RuntimeError(f"embed_backend_not_supported: {backend}")
