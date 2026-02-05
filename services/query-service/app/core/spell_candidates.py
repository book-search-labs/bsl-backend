from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None


_QWERTY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_QWERTY_POS: Dict[str, Tuple[int, int]] = {}
for r_idx, row in enumerate(_QWERTY_ROWS):
    for c_idx, ch in enumerate(row):
        _QWERTY_POS[ch] = (r_idx, c_idx)

_QWERTY_NEIGHBORS: Dict[str, List[str]] = {}
for ch, (r_idx, c_idx) in _QWERTY_POS.items():
    neighbors = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            coord = (r_idx + dr, c_idx + dc)
            for key, pos in _QWERTY_POS.items():
                if pos == coord:
                    neighbors.append(key)
    _QWERTY_NEIGHBORS[ch] = neighbors

_S_BASE = 0xAC00
_L_BASE = 0x1100
_V_BASE = 0x1161
_T_BASE = 0x11A7
_L_COUNT = 19
_V_COUNT = 21
_T_COUNT = 28
_N_COUNT = _V_COUNT * _T_COUNT

_L_LIST = [
    "ㄱ",
    "ㄲ",
    "ㄴ",
    "ㄷ",
    "ㄸ",
    "ㄹ",
    "ㅁ",
    "ㅂ",
    "ㅃ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅉ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]
_V_LIST = [
    "ㅏ",
    "ㅐ",
    "ㅑ",
    "ㅒ",
    "ㅓ",
    "ㅔ",
    "ㅕ",
    "ㅖ",
    "ㅗ",
    "ㅘ",
    "ㅙ",
    "ㅚ",
    "ㅛ",
    "ㅜ",
    "ㅝ",
    "ㅞ",
    "ㅟ",
    "ㅠ",
    "ㅡ",
    "ㅢ",
    "ㅣ",
]
_T_LIST = [
    "",
    "ㄱ",
    "ㄲ",
    "ㄳ",
    "ㄴ",
    "ㄵ",
    "ㄶ",
    "ㄷ",
    "ㄹ",
    "ㄺ",
    "ㄻ",
    "ㄼ",
    "ㄽ",
    "ㄾ",
    "ㄿ",
    "ㅀ",
    "ㅁ",
    "ㅂ",
    "ㅄ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]

_L_INDEX = {ch: idx for idx, ch in enumerate(_L_LIST)}
_V_INDEX = {ch: idx for idx, ch in enumerate(_V_LIST)}
_T_INDEX = {ch: idx for idx, ch in enumerate(_T_LIST)}

_JAMO_BASE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}

_JAMO_TO_KEY_CONS = {
    "ㅂ": "q",
    "ㅈ": "w",
    "ㄷ": "e",
    "ㄱ": "r",
    "ㅅ": "t",
    "ㅁ": "a",
    "ㄴ": "s",
    "ㅇ": "d",
    "ㄹ": "f",
    "ㅎ": "g",
    "ㅋ": "z",
    "ㅌ": "x",
    "ㅊ": "c",
    "ㅍ": "v",
}
_JAMO_TO_KEY_VOW = {
    "ㅛ": "y",
    "ㅕ": "u",
    "ㅑ": "i",
    "ㅐ": "o",
    "ㅔ": "p",
    "ㅗ": "h",
    "ㅓ": "j",
    "ㅏ": "k",
    "ㅣ": "l",
    "ㅠ": "b",
    "ㅜ": "n",
    "ㅡ": "m",
}
_KEY_TO_JAMO_CONS = {value: key for key, value in _JAMO_TO_KEY_CONS.items()}
_KEY_TO_JAMO_VOW = {value: key for key, value in _JAMO_TO_KEY_VOW.items()}


@dataclass
class SpellCandidate:
    text: str
    score: float
    reasons: List[str]

    def to_debug(self) -> dict:
        return {"text": self.text, "score": round(self.score, 4), "reason": self.reasons}


@dataclass
class SpellCandidateConfig:
    enabled: bool
    max_candidates: int
    top_k: int
    edit_distance_max: int
    keyboard_locale: str
    dict_backend: str
    dict_path: str
    dict_redis_url: Optional[str]
    dict_redis_key: str
    min_score: float


@dataclass
class DictEntry:
    canonical: str
    entry_type: Optional[str]


_DICT_CACHE: Dict[str, Tuple[float, Dict[str, DictEntry]]] = {}


def load_config() -> SpellCandidateConfig:
    return SpellCandidateConfig(
        enabled=os.getenv("QS_SPELL_CANDIDATE_ENABLE", "false").lower() in {"1", "true", "yes"},
        max_candidates=int(os.getenv("QS_SPELL_CANDIDATE_MAX", "50")),
        top_k=int(os.getenv("QS_SPELL_CANDIDATE_TOPK", "5")),
        edit_distance_max=int(os.getenv("QS_SPELL_EDIT_DISTANCE_MAX", "2")),
        keyboard_locale=os.getenv("QS_SPELL_KEYBOARD_LOCALE", "both").lower(),
        dict_backend=os.getenv("QS_SPELL_DICT_BACKEND", "file").lower(),
        dict_path=os.getenv("QS_SPELL_DICT_PATH", "data/dict/spell_aliases.jsonl"),
        dict_redis_url=os.getenv("QS_SPELL_DICT_REDIS_URL"),
        dict_redis_key=os.getenv("QS_SPELL_DICT_REDIS_KEY", "qs:spell:dict"),
        min_score=float(os.getenv("QS_SPELL_CANDIDATE_MIN_SCORE", "0.0")),
    )


def get_generator() -> Optional["SpellCandidateGenerator"]:
    config = load_config()
    if not config.enabled:
        return None
    dictionary = _load_dictionary(config)
    return SpellCandidateGenerator(config, dictionary)


def _load_dictionary(config: SpellCandidateConfig) -> Dict[str, DictEntry]:
    backend = config.dict_backend
    if backend == "redis":
        return _load_dictionary_redis(config)
    return _load_dictionary_file(config)


def _load_dictionary_file(config: SpellCandidateConfig) -> Dict[str, DictEntry]:
    path = config.dict_path
    if not path:
        return {}
    resolved_path = path
    if not os.path.isabs(path) and not os.path.exists(path):
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        candidate = os.path.join(base, path)
        if os.path.exists(candidate):
            resolved_path = candidate
    if not os.path.exists(resolved_path):
        return {}
    mtime = os.path.getmtime(resolved_path)
    cache_key = f"file::{resolved_path}"
    cached = _DICT_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]
    mapping: Dict[str, DictEntry] = {}
    with open(resolved_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            canonical = (item.get("canonical") or item.get("key") or "").strip()
            if not canonical:
                continue
            entry_type = item.get("type") or item.get("entry_type")
            variants = item.get("variants") or item.get("aliases") or item.get("values") or []
            if isinstance(variants, str):
                variants = [variants]
            for variant in [canonical, *variants]:
                if not isinstance(variant, str):
                    continue
                key = variant.strip().lower()
                if not key:
                    continue
                mapping[key] = DictEntry(canonical=canonical, entry_type=entry_type)
    _DICT_CACHE[cache_key] = (mtime, mapping)
    return mapping


def _load_dictionary_redis(config: SpellCandidateConfig) -> Dict[str, DictEntry]:
    if redis is None or not config.dict_redis_url:
        return {}
    cache_key = f"redis::{config.dict_redis_url}::{config.dict_redis_key}"
    cached = _DICT_CACHE.get(cache_key)
    if cached:
        return cached[1]
    mapping: Dict[str, DictEntry] = {}
    try:
        client = redis.Redis.from_url(config.dict_redis_url, decode_responses=True)
        data = client.hgetall(config.dict_redis_key)
        for variant, canonical in data.items():
            if not variant or not canonical:
                continue
            mapping[variant.strip().lower()] = DictEntry(canonical=canonical.strip(), entry_type=None)
    except Exception:
        return {}
    _DICT_CACHE[cache_key] = (0.0, mapping)
    return mapping


class SpellCandidateGenerator:
    def __init__(self, config: SpellCandidateConfig, dictionary: Dict[str, DictEntry]) -> None:
        self._config = config
        self._dictionary = dictionary

    def generate(self, text: str) -> List[SpellCandidate]:
        original = (text or "").strip()
        if not original:
            return []
        candidate_map: Dict[str, set[str]] = {}

        def add(candidate: str, reason: str) -> None:
            if not candidate or candidate == original:
                return
            if len(candidate_map) >= self._config.max_candidates:
                return
            entry = candidate_map.setdefault(candidate, set())
            entry.add(reason)

        for variant in _whitespace_variants(original):
            add(variant, "space")

        for variant in self._dictionary_variants(original):
            add(variant, "dict_hit")

        for variant in _keyboard_variants(original, self._config.keyboard_locale, self._config.max_candidates):
            add(variant, "kbd_adj")

        for variant in _edit_variants(original, self._config.edit_distance_max, self._config.max_candidates):
            add(variant, "edit1")

        candidates = []
        for candidate, reasons in candidate_map.items():
            score = _score_candidate(original, candidate, reasons)
            if score < self._config.min_score:
                continue
            candidates.append(SpellCandidate(text=candidate, score=score, reasons=sorted(reasons)))

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[: max(self._config.top_k, 0)]

    def _dictionary_variants(self, text: str) -> Iterable[str]:
        if not self._dictionary:
            return []
        lowered = text.lower()
        variants = []
        for variant, entry in self._dictionary.items():
            if variant and variant in lowered:
                replaced = re.sub(re.escape(variant), entry.canonical, text, flags=re.IGNORECASE)
                if replaced and replaced != text:
                    variants.append(replaced)
        return variants


def _whitespace_variants(text: str) -> List[str]:
    variants = []
    collapsed = re.sub(r"\s+", " ", text).strip()
    if collapsed and collapsed != text:
        variants.append(collapsed)
    nospace = re.sub(r"\s+", "", text)
    if nospace and nospace != text:
        variants.append(nospace)
    spaced_volume = re.sub(r"(\d+)(권)", r"\1 \2", collapsed)
    if spaced_volume and spaced_volume != text:
        variants.append(spaced_volume)
    return variants


def _keyboard_variants(text: str, locale: str, limit: int) -> List[str]:
    if locale not in {"ko", "en", "both"}:
        return []
    variants = []
    for idx, ch in enumerate(text):
        if len(variants) >= limit:
            break
        for repl in _adjacent_chars(ch, locale):
            variant = text[:idx] + repl + text[idx + 1 :]
            if variant != text:
                variants.append(variant)
                if len(variants) >= limit:
                    break
    return variants


def _adjacent_chars(ch: str, locale: str) -> List[str]:
    results: List[str] = []
    lowered = ch.lower()
    if locale in {"en", "both"} and lowered in _QWERTY_NEIGHBORS:
        for neighbor in _QWERTY_NEIGHBORS[lowered]:
            results.append(neighbor.upper() if ch.isupper() else neighbor)
    if locale in {"ko", "both"} and _is_hangul_syllable(ch):
        results.extend(_hangul_adjacent(ch))
    return results


def _hangul_adjacent(ch: str) -> List[str]:
    decomposed = _decompose_syllable(ch)
    if decomposed is None:
        return []
    l_jamo, v_jamo, t_jamo = decomposed
    results = []
    for repl in _adjacent_jamo(l_jamo, _JAMO_TO_KEY_CONS, _KEY_TO_JAMO_CONS):
        syllable = _compose_syllable(repl, v_jamo, t_jamo)
        if syllable:
            results.append(syllable)
    for repl in _adjacent_jamo(v_jamo, _JAMO_TO_KEY_VOW, _KEY_TO_JAMO_VOW):
        syllable = _compose_syllable(l_jamo, repl, t_jamo)
        if syllable:
            results.append(syllable)
    if t_jamo:
        for repl in _adjacent_jamo(t_jamo, _JAMO_TO_KEY_CONS, _KEY_TO_JAMO_CONS):
            syllable = _compose_syllable(l_jamo, v_jamo, repl)
            if syllable:
                results.append(syllable)
    return results


def _adjacent_jamo(
    jamo: str,
    jamo_to_key: Dict[str, str],
    key_to_jamo: Dict[str, str],
) -> List[str]:
    base = _JAMO_BASE.get(jamo, jamo)
    key = jamo_to_key.get(base)
    if not key:
        return []
    neighbors = _QWERTY_NEIGHBORS.get(key, [])
    results = []
    for neighbor in neighbors:
        mapped = key_to_jamo.get(neighbor)
        if mapped:
            results.append(mapped)
    return results


def _edit_variants(text: str, max_distance: int, limit: int) -> List[str]:
    if max_distance < 1:
        return []
    variants = []
    tokens = text.split()
    for idx, token in enumerate(tokens):
        if len(variants) >= limit:
            break
        if len(token) < 2:
            continue
        for pos in range(len(token)):
            candidate_token = token[:pos] + token[pos + 1 :]
            if candidate_token:
                candidate = _replace_token(tokens, idx, candidate_token)
                variants.append(candidate)
                if len(variants) >= limit:
                    break
        for pos in range(len(token) - 1):
            if token[pos] == token[pos + 1]:
                continue
            swapped = token[:pos] + token[pos + 1] + token[pos] + token[pos + 2 :]
            candidate = _replace_token(tokens, idx, swapped)
            variants.append(candidate)
            if len(variants) >= limit:
                break
    if max_distance >= 2 and len(variants) < limit:
        for candidate in list(variants)[: max(1, limit // 3)]:
            if len(variants) >= limit:
                break
            for pos in range(len(candidate)):
                double_edit = candidate[:pos] + candidate[pos + 1 :]
                if double_edit and double_edit != candidate:
                    variants.append(double_edit)
                    if len(variants) >= limit:
                        break
    return variants


def _replace_token(tokens: List[str], idx: int, token: str) -> str:
    updated = list(tokens)
    updated[idx] = token
    return " ".join(updated)


def _score_candidate(original: str, candidate: str, reasons: Iterable[str]) -> float:
    norm_orig = _normalize(original)
    norm_cand = _normalize(candidate)
    if not norm_orig or not norm_cand:
        return 0.0
    if _numeric_mismatch(original, candidate):
        return 0.0
    if _volume_mismatch(original, candidate):
        return 0.0
    distance = _edit_distance(norm_orig, norm_cand)
    ratio = distance / max(len(norm_orig), 1)
    score = max(0.0, 1.0 - ratio)
    reason_set = set(reasons)
    if "dict_hit" in reason_set:
        score += 0.2
    if "kbd_adj" in reason_set:
        score += 0.05
    if "edit1" in reason_set:
        score += 0.02
    return min(score, 1.0)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _numeric_mismatch(original: str, candidate: str) -> bool:
    tokens = re.findall(r"[0-9][0-9-]{2,}", original or "")
    digits = [re.sub(r"[^0-9]", "", token) for token in tokens]
    digits = [token for token in digits if len(token) >= 4]
    if not digits:
        return False
    cand_digits = re.sub(r"[^0-9]", "", candidate or "")
    return any(token not in cand_digits for token in digits)


def _volume_numbers(text: str) -> set[str]:
    matches = re.findall(r"(\d+)\s*(권|권차|vol(?:ume)?|v\.?)(?!\w)", text, flags=re.IGNORECASE)
    return {match[0] for match in matches if match and match[0]}


def _volume_mismatch(original: str, candidate: str) -> bool:
    original_volumes = _volume_numbers(original or "")
    if not original_volumes:
        return False
    candidate_volumes = _volume_numbers(candidate or "")
    return not original_volumes.issubset(candidate_volumes)


def _is_hangul_syllable(ch: str) -> bool:
    code = ord(ch)
    return _S_BASE <= code <= 0xD7A3


def _decompose_syllable(ch: str) -> Optional[Tuple[str, str, str]]:
    code = ord(ch)
    if not _is_hangul_syllable(ch):
        return None
    s_index = code - _S_BASE
    l_index = s_index // _N_COUNT
    v_index = (s_index % _N_COUNT) // _T_COUNT
    t_index = s_index % _T_COUNT
    l_jamo = _L_LIST[l_index]
    v_jamo = _V_LIST[v_index]
    t_jamo = _T_LIST[t_index]
    return l_jamo, v_jamo, t_jamo


def _compose_syllable(l_jamo: str, v_jamo: str, t_jamo: str) -> Optional[str]:
    l_index = _L_INDEX.get(l_jamo)
    v_index = _V_INDEX.get(v_jamo)
    if l_index is None or v_index is None:
        return None
    t_index = _T_INDEX.get(t_jamo, 0)
    code = _S_BASE + (l_index * _N_COUNT) + (v_index * _T_COUNT) + t_index
    return chr(code)
