import argparse
import json
from pathlib import Path


def load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("PyYAML is required (pip install pyyaml)") from exc
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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


def apply_transform(raw, transform):
    value = raw
    if value is None:
        value = transform.get("default")
    numeric = to_number(value)
    if transform.get("log1p"):
        numeric = max(0.0, numeric)
        numeric = __import__("math").log1p(numeric)
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


def compute_derived(name, query_text, raw_features):
    if name == "query_len":
        return len((query_text or "").strip())
    if name == "has_recover":
        labels = raw_features.get("edition_labels") or []
        return any(isinstance(label, str) and label.lower() == "recover" for label in labels)
    if name == "freshness_days":
        issued_year = raw_features.get("issued_year")
        if issued_year is None:
            return None
        try:
            issued_year = int(issued_year)
        except Exception:
            return None
        current_year = __import__("datetime").date.today().year
        return max(0, current_year - issued_year) * 365
    return None


def build_feature_vector(spec, record):
    query_text = record.get("query") or ""
    raw_features = record.get("features") or {}
    kv_features = record.get("kv") or {}
    output = {}

    for feature in spec.get("features", []):
        name = feature.get("name")
        source = (feature.get("source") or "").lower()
        transform = feature.get("transform") or {}
        if source == "request":
            raw = raw_features.get(name)
        elif source == "kv":
            raw = kv_features.get(name)
        elif source == "derived":
            raw = compute_derived(name, query_text, raw_features)
        else:
            raw = None
        output[name] = apply_transform(raw, transform)
    return output


def main():
    parser = argparse.ArgumentParser(description="Offline feature builder (spec-driven)")
    parser.add_argument("--spec", default="config/features.yaml")
    parser.add_argument("--input", help="JSONL input with {query, doc_id, features, kv}")
    parser.add_argument("--output", help="JSONL output path", default="-")
    args = parser.parse_args()

    spec = load_yaml(Path(args.spec))
    feature_set_version = spec.get("feature_set_version", "fs_v1")

    records = []
    if args.input:
        with open(args.input, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
    else:
        records = [
            {
                "query": "harry potter",
                "doc_id": "b1",
                "features": {"rrf_score": 0.167, "lex_rank": 1, "vec_rank": 2, "issued_year": 1999, "volume": 1},
                "kv": {"ctr_7d": 0.12, "popularity_30d": 25.4},
            }
        ]

    lines = []
    for record in records:
        vector = build_feature_vector(spec, record)
        lines.append(
            {
                "doc_id": record.get("doc_id"),
                "query": record.get("query"),
                "feature_set_version": feature_set_version,
                "features": vector,
            }
        )

    output_text = "\n".join(json.dumps(line, ensure_ascii=True) for line in lines)
    if args.output == "-":
        print(output_text)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output_text + "\n")


if __name__ == "__main__":
    main()
