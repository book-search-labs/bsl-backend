import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

import math


try:
    import onnxruntime  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    onnxruntime = None
    np = None


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
