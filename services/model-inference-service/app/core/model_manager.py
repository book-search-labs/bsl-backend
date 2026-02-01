from typing import Dict, Optional, Tuple

from app.core.models import BaseModel, OnnxCrossEncoderModel, OnnxRerankModel, ToyRerankModel
from app.core.registry import ModelRegistry, ModelSpec
from app.core.settings import SETTINGS


class ModelManager:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry
        self._models: Dict[str, BaseModel] = {}
        self._model_status: Dict[str, str] = {}

    def get_model(self, task: str, requested_id: Optional[str]) -> Tuple[Optional[ModelSpec], Optional[BaseModel]]:
        spec = self._registry.resolve(task, requested_id or SETTINGS.default_model or None)
        if spec is None:
            return None, None
        model = self._models.get(spec.model_id)
        if model is None:
            model = self._load_model(spec)
        return spec, model

    def _load_model(self, spec: ModelSpec) -> Optional[BaseModel]:
        if spec.backend == "onnx":
            try:
                path = self._resolve_artifact_path(spec)
                model = OnnxRerankModel(
                    path,
                    spec.input_name,
                    spec.output_name,
                    spec.feature_order or [],
                    SETTINGS.onnx_providers,
                )
                self._models[spec.model_id] = model
                self._model_status[spec.model_id] = "ready"
                return model
            except Exception:
                self._model_status[spec.model_id] = "error"
                return None
        if spec.backend == "onnx_cross":
            try:
                path = self._resolve_artifact_path(spec)
                tokenizer_path = self._resolve_tokenizer_path(spec)
                max_len = spec.max_len or 256
                model = OnnxCrossEncoderModel(
                    path,
                    tokenizer_path,
                    max_len,
                    spec.output_name,
                    spec.logit_index,
                    SETTINGS.onnx_providers,
                )
                self._models[spec.model_id] = model
                self._model_status[spec.model_id] = "ready"
                return model
            except Exception:
                self._model_status[spec.model_id] = "error"
                return None
        model = ToyRerankModel()
        self._models[spec.model_id] = model
        self._model_status[spec.model_id] = "ready"
        return model

    def model_status(self, model_id: str) -> str:
        return self._model_status.get(model_id, "unknown")

    def is_loaded(self, model_id: str) -> bool:
        return model_id in self._models

    def _resolve_artifact_path(self, spec: ModelSpec) -> str:
        uri = spec.artifact_uri
        if uri.startswith("local://"):
            uri = uri.replace("local://", "")
        if uri.startswith("/"):
            return uri
        if "://" in uri:
            # Remote URIs require external sync into local model dir.
            return f"{SETTINGS.model_dir.rstrip('/')}/{spec.model_id}.onnx"
        return f"{SETTINGS.model_dir.rstrip('/')}/{uri}"

    def _resolve_tokenizer_path(self, spec: ModelSpec) -> str:
        uri = spec.tokenizer_uri or ""
        if uri.startswith("local://"):
            uri = uri.replace("local://", "")
        if uri.startswith("/"):
            return uri
        if "://" in uri:
            return f"{SETTINGS.model_dir.rstrip('/')}/{spec.model_id}.tokenizer.json"
        if uri:
            return f"{SETTINGS.model_dir.rstrip('/')}/{uri}"
        return f"{SETTINGS.model_dir.rstrip('/')}/{spec.model_id}.tokenizer.json"
