from typing import Optional

from app.core.models import BaseSpellModel, OnnxSpellModel, ToySpellModel
from app.core.settings import SETTINGS


class SpellModelManager:
    def __init__(self) -> None:
        self._model: Optional[BaseSpellModel] = None
        self._model_id: str = SETTINGS.spell_model_id or "spell_default"

    def get_model(self, requested_id: Optional[str]) -> BaseSpellModel:
        if requested_id and self._model_id and requested_id != self._model_id:
            raise RuntimeError("spell_model_not_found")
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def model_id(self) -> str:
        return self._model_id

    def _load_model(self) -> BaseSpellModel:
        backend = SETTINGS.spell_backend
        if backend == "onnx":
            try:
                if not SETTINGS.spell_model_path or not SETTINGS.spell_tokenizer_path:
                    raise RuntimeError("spell_model_path_or_tokenizer_missing")
                output_name = SETTINGS.spell_output_name or None
                return OnnxSpellModel(
                    SETTINGS.spell_model_path,
                    SETTINGS.spell_tokenizer_path,
                    SETTINGS.spell_max_len,
                    output_name,
                    SETTINGS.spell_decoder_start_id,
                    SETTINGS.onnx_providers,
                )
            except Exception:
                if SETTINGS.spell_fallback.lower() in {"toy", "mock"}:
                    return ToySpellModel()
                raise
        if backend == "toy":
            return ToySpellModel()
        raise RuntimeError(f"spell_backend_not_supported: {backend}")
