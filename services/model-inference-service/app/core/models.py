import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

import math


try:
    import onnxruntime  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    onnxruntime = None
    np = None

try:
    from tokenizers import Tokenizer  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Tokenizer = None


FEATURE_ORDER = ["rrf_score", "lex_rank", "vec_rank", "issued_year", "volume", "has_recover"]


@dataclass
class PairFeatures:
    lex_rank: Optional[int] = None
    vec_rank: Optional[int] = None
    rrf_score: Optional[float] = None
    issued_year: Optional[int] = None
    volume: Optional[int] = None
    edition_labels: Optional[List[str]] = None


@dataclass
class ScoreResult:
    score: float
    debug: dict


class BaseModel:
    def score(self, pairs: List[dict]) -> List[ScoreResult]:
        raise NotImplementedError


class BaseEmbedModel:
    def embed(self, texts: List[str], normalize: bool) -> List[List[float]]:
        raise NotImplementedError


@dataclass
class SpellResult:
    corrected: str
    confidence: float


class BaseSpellModel:
    def correct(self, texts: List[str]) -> List[SpellResult]:
        raise NotImplementedError


class ToyRerankModel(BaseModel):
    RANK_BASE = 60.0

    def score(self, pairs: List[dict]) -> List[ScoreResult]:
        results = []
        for pair in pairs:
            features = pair.get("features") or {}
            lex_rank = features.get("lex_rank")
            vec_rank = features.get("vec_rank")
            base_score = features.get("rrf_score")
            issued_year = features.get("issued_year")
            volume = features.get("volume")
            edition_labels = features.get("edition_labels")

            base = base_score or 0.0
            lex_bonus = 0.0 if lex_rank is None else 1.0 / (self.RANK_BASE + lex_rank)
            vec_bonus = 0.0 if vec_rank is None else 1.0 / (self.RANK_BASE + vec_rank)
            freshness_bonus = self._freshness_bonus(issued_year)
            slot_bonus = self._slot_bonus(volume, edition_labels)

            score = base + (2.0 * lex_bonus) + vec_bonus + (0.2 * freshness_bonus) + slot_bonus
            results.append(
                ScoreResult(
                    score=score,
                    debug={
                        "base_rrf": base,
                        "lex_bonus": lex_bonus,
                        "vec_bonus": vec_bonus,
                        "freshness_bonus": freshness_bonus,
                        "slot_bonus": slot_bonus,
                        "lex_rank": lex_rank,
                        "vec_rank": vec_rank,
                    },
                )
            )
        return results

    def _freshness_bonus(self, issued_year: Optional[int]) -> float:
        if issued_year is None:
            return 0.0
        raw = (issued_year - 1980) / 100.0
        if raw < 0.0:
            return 0.0
        if raw > 0.5:
            return 0.5
        return raw

    def _slot_bonus(self, volume: Optional[int], edition_labels: Optional[List[str]]) -> float:
        bonus = 0.0
        if volume and volume > 0:
            bonus += 0.10
        if edition_labels:
            for label in edition_labels:
                if isinstance(label, str) and label.lower() == "recover":
                    bonus += 0.05
                    break
        return bonus


class OnnxRerankModel(BaseModel):
    def __init__(
        self,
        path: str,
        input_name: Optional[str],
        output_name: Optional[str],
        feature_order: List[str],
        providers: Optional[Iterable[str]] = None,
    ):
        if onnxruntime is None or np is None:
            raise RuntimeError("onnxruntime not available")
        if not os.path.exists(path):
            raise RuntimeError(f"onnx model missing: {path}")
        provider_list = list(providers) if providers else ["CPUExecutionProvider"]
        self._session = onnxruntime.InferenceSession(path, providers=provider_list)
        self._input_name = input_name or self._session.get_inputs()[0].name
        self._output_name = output_name or self._session.get_outputs()[0].name
        self._feature_order = feature_order or FEATURE_ORDER

    def score(self, pairs: List[dict]) -> List[ScoreResult]:
        features = [self._feature_vector(pair.get("features") or {}) for pair in pairs]
        inputs = np.asarray(features, dtype=np.float32)
        outputs = self._session.run([self._output_name], {self._input_name: inputs})[0]
        scores = outputs.flatten().tolist()
        results = []
        for score in scores:
            results.append(ScoreResult(score=float(score), debug={"backend": "onnx"}))
        return results

    def _feature_vector(self, features: dict) -> List[float]:
        lex_rank = features.get("lex_rank")
        vec_rank = features.get("vec_rank")
        rrf_score = features.get("rrf_score")
        issued_year = features.get("issued_year")
        volume = features.get("volume")
        edition_labels = features.get("edition_labels")
        has_recover = 0.0
        if edition_labels:
            for label in edition_labels:
                if isinstance(label, str) and label.lower() == "recover":
                    has_recover = 1.0
                    break

        values = {
            "rrf_score": float(rrf_score or 0.0),
            "lex_rank": float(lex_rank or 0.0),
            "vec_rank": float(vec_rank or 0.0),
            "issued_year": float(issued_year or 0.0),
            "volume": float(volume or 0.0),
            "has_recover": float(has_recover),
        }
        return [values.get(name, 0.0) for name in self._feature_order]


class ToyEmbedModel(BaseEmbedModel):
    def __init__(self, dim: int) -> None:
        self._dim = max(1, dim)

    def embed(self, texts: List[str], normalize: bool) -> List[List[float]]:
        results = []
        for text in texts:
            values = self._embed_one(text or "")
            if normalize:
                norm = math.sqrt(sum(v * v for v in values)) or 1.0
                values = [v / norm for v in values]
            results.append(values)
        return results

    def _embed_one(self, text: str) -> List[float]:
        import hashlib
        import random

        seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()[:8]
        seed = int.from_bytes(seed_bytes, "big", signed=False)
        rng = random.Random(seed)
        return [rng.random() for _ in range(self._dim)]


class OnnxEmbedModel(BaseEmbedModel):
    def __init__(
        self,
        model_path: str,
        tokenizer_path: str,
        max_len: int,
        output_name: str | None = None,
        providers: Optional[Iterable[str]] = None,
    ):
        if onnxruntime is None or np is None:
            raise RuntimeError("onnxruntime not available")
        if Tokenizer is None:
            raise RuntimeError("tokenizers not available")
        if not os.path.exists(model_path):
            raise RuntimeError(f"onnx embed model missing: {model_path}")
        if not os.path.exists(tokenizer_path):
            raise RuntimeError(f"tokenizer missing: {tokenizer_path}")
        provider_list = list(providers) if providers else ["CPUExecutionProvider"]
        self._session = onnxruntime.InferenceSession(model_path, providers=provider_list)
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._max_len = max(8, max_len)
        self._output_name = output_name or self._session.get_outputs()[0].name
        self._input_names = [item.name for item in self._session.get_inputs()]
        self._tokenizer.enable_truncation(max_length=self._max_len)
        self._tokenizer.enable_padding(length=self._max_len)

    def embed(self, texts: List[str], normalize: bool) -> List[List[float]]:
        if not texts:
            return []
        encodings = self._tokenizer.encode_batch(texts)
        inputs = {
            "input_ids": np.asarray([enc.ids for enc in encodings], dtype=np.int64),
            "attention_mask": np.asarray([enc.attention_mask for enc in encodings], dtype=np.int64),
        }
        if "token_type_ids" in self._input_names:
            inputs["token_type_ids"] = np.asarray([enc.type_ids for enc in encodings], dtype=np.int64)
        payload = {name: inputs[name] for name in self._input_names if name in inputs}
        outputs = self._session.run([self._output_name], payload)[0]
        vectors = self._pool(outputs, inputs["attention_mask"])
        if normalize:
            vectors = self._l2_normalize(vectors)
        return vectors.tolist()

    def _pool(self, outputs, attention_mask):
        if outputs.ndim == 2:
            return outputs
        if outputs.ndim == 3:
            mask = attention_mask[:, :, None].astype(np.float32)
            summed = (outputs * mask).sum(axis=1)
            counts = mask.sum(axis=1)
            counts[counts == 0] = 1.0
            return summed / counts
        return outputs.reshape(outputs.shape[0], -1)

    def _l2_normalize(self, vectors):
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms


class OnnxCrossEncoderModel(BaseModel):
    def __init__(
        self,
        model_path: str,
        tokenizer_path: str,
        max_len: int,
        output_name: Optional[str],
        logit_index: Optional[int],
        providers: Optional[Iterable[str]] = None,
    ):
        if onnxruntime is None or np is None:
            raise RuntimeError("onnxruntime not available")
        if Tokenizer is None:
            raise RuntimeError("tokenizers not available")
        if not os.path.exists(model_path):
            raise RuntimeError(f"onnx rerank model missing: {model_path}")
        if not os.path.exists(tokenizer_path):
            raise RuntimeError(f"tokenizer missing: {tokenizer_path}")
        provider_list = list(providers) if providers else ["CPUExecutionProvider"]
        self._session = onnxruntime.InferenceSession(model_path, providers=provider_list)
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._max_len = max(8, max_len)
        self._output_name = output_name or self._session.get_outputs()[0].name
        self._input_names = [item.name for item in self._session.get_inputs()]
        self._logit_index = logit_index
        self._tokenizer.enable_truncation(max_length=self._max_len)
        self._tokenizer.enable_padding(length=self._max_len)

    def score(self, pairs: List[dict]) -> List[ScoreResult]:
        if not pairs:
            return []
        encodings = self._tokenizer.encode_batch(
            [(pair.get("query", ""), pair.get("doc", "")) for pair in pairs]
        )
        inputs = {
            "input_ids": np.asarray([enc.ids for enc in encodings], dtype=np.int64),
            "attention_mask": np.asarray([enc.attention_mask for enc in encodings], dtype=np.int64),
        }
        if "token_type_ids" in self._input_names:
            inputs["token_type_ids"] = np.asarray([enc.type_ids for enc in encodings], dtype=np.int64)
        payload = {name: inputs[name] for name in self._input_names if name in inputs}
        outputs = self._session.run([self._output_name], payload)[0]
        scores = self._extract_scores(outputs)
        results = []
        for score in scores:
            results.append(ScoreResult(score=float(score), debug={"backend": "onnx_cross"}))
        return results

    def _extract_scores(self, outputs):
        if outputs.ndim == 1:
            return outputs
        if outputs.ndim == 2:
            if outputs.shape[1] == 1:
                return outputs[:, 0]
            idx = self._logit_index if self._logit_index is not None else 1
            idx = max(0, min(idx, outputs.shape[1] - 1))
            return outputs[:, idx]
        return outputs.reshape(outputs.shape[0], -1)[:, 0]


class ToySpellModel(BaseSpellModel):
    def __init__(self) -> None:
        self._mapping = {
            "harry pottre": "harry potter",
            "haarry potter": "harry potter",
            "해리 포터": "해리포터",
            "정약    용  자서전 01권": "정약용 자서전 1권",
        }

    def correct(self, texts: List[str]) -> List[SpellResult]:
        results = []
        for text in texts:
            normalized = re.sub(r"\s+", " ", text or "").strip()
            candidate = self._mapping.get((text or "").lower()) or self._mapping.get(normalized.lower())
            corrected = candidate or normalized or text
            confidence = 0.7 if corrected and corrected != text else 0.1
            results.append(SpellResult(corrected=corrected, confidence=confidence))
        return results


class OnnxSpellModel(BaseSpellModel):
    def __init__(
        self,
        model_path: str,
        tokenizer_path: str,
        max_len: int,
        output_name: Optional[str],
        decoder_start_id: int,
        providers: Optional[Iterable[str]] = None,
    ):
        if onnxruntime is None or np is None:
            raise RuntimeError("onnxruntime not available")
        if Tokenizer is None:
            raise RuntimeError("tokenizers not available")
        if not os.path.exists(model_path):
            raise RuntimeError(f"onnx spell model missing: {model_path}")
        if not os.path.exists(tokenizer_path):
            raise RuntimeError(f"tokenizer missing: {tokenizer_path}")
        provider_list = list(providers) if providers else ["CPUExecutionProvider"]
        self._session = onnxruntime.InferenceSession(model_path, providers=provider_list)
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._max_len = max(4, max_len)
        self._output_name = output_name or self._session.get_outputs()[0].name
        self._input_names = [item.name for item in self._session.get_inputs()]
        self._decoder_start_id = decoder_start_id
        self._tokenizer.enable_truncation(max_length=self._max_len)
        self._tokenizer.enable_padding(length=self._max_len)

    def correct(self, texts: List[str]) -> List[SpellResult]:
        if not texts:
            return []
        encodings = self._tokenizer.encode_batch(texts)
        inputs = {
            "input_ids": np.asarray([enc.ids for enc in encodings], dtype=np.int64),
            "attention_mask": np.asarray([enc.attention_mask for enc in encodings], dtype=np.int64),
        }
        if "token_type_ids" in self._input_names:
            inputs["token_type_ids"] = np.asarray([enc.type_ids for enc in encodings], dtype=np.int64)
        if "decoder_input_ids" in self._input_names:
            batch = len(texts)
            inputs["decoder_input_ids"] = np.full((batch, 1), self._decoder_start_id, dtype=np.int64)
        if "decoder_attention_mask" in self._input_names and "decoder_input_ids" in inputs:
            inputs["decoder_attention_mask"] = np.ones_like(inputs["decoder_input_ids"], dtype=np.int64)
        payload = {name: inputs[name] for name in self._input_names if name in inputs}
        outputs = self._session.run([self._output_name], payload)[0]
        return self._decode_outputs(outputs, texts)

    def _decode_outputs(self, outputs, texts: List[str]) -> List[SpellResult]:
        if outputs is None:
            return [SpellResult(corrected=text, confidence=0.0) for text in texts]
        if outputs.ndim == 1:
            outputs = outputs.reshape(1, -1)
        if outputs.ndim == 2:
            token_ids = outputs
        else:
            token_ids = np.argmax(outputs, axis=-1)
        results = []
        for idx, ids in enumerate(token_ids):
            id_list = [int(val) for val in ids if int(val) >= 0]
            corrected = self._tokenizer.decode(id_list, skip_special_tokens=True).strip()
            if not corrected:
                corrected = texts[idx]
            confidence = 0.7 if corrected != texts[idx] else 0.2
            results.append(SpellResult(corrected=corrected, confidence=confidence))
        return results
