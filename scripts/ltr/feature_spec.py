import datetime
import json
import math
from pathlib import Path


def load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyYAML is required (pip install pyyaml)") from exc
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def feature_order(spec: dict) -> list[str]:
    return [str(feature.get("name")) for feature in spec.get("features", []) if feature.get("name")]


def to_number(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def apply_transform(raw, transform: dict):
    value = raw
    if value is None:
        value = transform.get("default")
    numeric = to_number(value)
    if transform.get("log1p"):
        numeric = max(0.0, numeric)
        numeric = math.log1p(numeric)
    clip = transform.get("clip") or {}
    if clip.get("min") is not None:
        numeric = max(float(clip["min"]), numeric)
    if clip.get("max") is not None:
        numeric = min(float(clip["max"]), numeric)
    bucketize = transform.get("bucketize")
    if isinstance(bucketize, dict):
        bucketize = bucketize.get("boundaries")
    if isinstance(bucketize, list) and bucketize:
        bucket = 0
        for boundary in bucketize:
            if numeric <= float(boundary):
                return float(bucket)
            bucket += 1
        return float(bucket)
    return numeric


def compute_derived(name: str, query_text: str, raw_features: dict):
    if name == "query_len":
        return len((query_text or "").strip())
    if name == "has_recover":
        labels = raw_features.get("edition_labels") or raw_features.get("editionLabels") or []
        return any(isinstance(label, str) and label.lower() == "recover" for label in labels)
    if name == "freshness_days":
        issued_year = raw_features.get("issued_year") or raw_features.get("issuedYear")
        if issued_year is None:
            return None
        try:
            issued_year = int(issued_year)
        except Exception:
            return None
        current_year = datetime.date.today().year
        return max(0, current_year - issued_year) * 365
    return None


def build_feature_vector(spec: dict, record: dict) -> dict:
    query_text = record.get("query") or record.get("query_text") or record.get("query_raw") or ""
    raw_features = record.get("features") or {}
    kv_features = record.get("kv") or {}
    output = {}

    for feature in spec.get("features", []):
        name = feature.get("name")
        if not name:
            continue
        source = (feature.get("source") or "").lower()
        transform = feature.get("transform") or {}
        if source == "request":
            raw = raw_features.get(name)
            if raw is None:
                raw = record.get(name)
        elif source == "kv":
            raw = kv_features.get(name)
            if raw is None:
                raw = record.get(name)
        elif source == "derived":
            combined = {}
            combined.update(record)
            if isinstance(raw_features, dict):
                combined.update(raw_features)
            raw = compute_derived(name, query_text, combined)
        else:
            raw = None
        output[name] = apply_transform(raw, transform)
    return output


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records
