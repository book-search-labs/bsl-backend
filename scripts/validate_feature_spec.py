import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "config" / "features.yaml"


def load_yaml(path: Path) -> dict | None:
    try:
        import yaml  # type: ignore
    except Exception:
        print("[SKIP] PyYAML not installed; skipping feature spec validation")
        return None
    if not path.exists():
        print(f"[FAIL] feature spec not found: {path}")
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def validate(spec: dict) -> list[str]:
    issues: list[str] = []
    if not isinstance(spec, dict):
        issues.append("spec root must be a mapping")
        return issues
    feature_set_version = spec.get("feature_set_version")
    if not feature_set_version:
        issues.append("feature_set_version is required")
    features = spec.get("features")
    if not isinstance(features, list) or not features:
        issues.append("features list is required")
        return issues

    seen = set()
    valid_types = {"float", "int", "bool", "categorical"}
    valid_keys = {"doc", "query", "query_doc"}
    valid_sources = {"request", "kv", "derived"}

    for idx, feature in enumerate(features):
        if not isinstance(feature, dict):
            issues.append(f"features[{idx}] must be a mapping")
            continue
        name = feature.get("name")
        if not name:
            issues.append(f"features[{idx}].name is required")
            continue
        if name in seen:
            issues.append(f"duplicate feature name: {name}")
        seen.add(name)

        ftype = str(feature.get("type", "")).lower()
        if ftype not in valid_types:
            issues.append(f"{name}: invalid type '{ftype}'")

        key_type = str(feature.get("key_type", "")).lower()
        if key_type not in valid_keys:
            issues.append(f"{name}: invalid key_type '{key_type}'")

        source = str(feature.get("source", "")).lower()
        if source not in valid_sources:
            issues.append(f"{name}: invalid source '{source}'")

        transform = feature.get("transform") or {}
        if isinstance(transform, dict):
            clip = transform.get("clip")
            if isinstance(clip, dict):
                clip_min = clip.get("min")
                clip_max = clip.get("max")
                if clip_min is not None and clip_max is not None:
                    try:
                        if float(clip_min) > float(clip_max):
                            issues.append(f"{name}: clip min > max")
                    except Exception:
                        issues.append(f"{name}: clip min/max not numeric")
        else:
            issues.append(f"{name}: transform must be mapping when provided")
    return issues


def main() -> int:
    spec = load_yaml(SPEC_PATH)
    if spec is None:
        return 0
    issues = validate(spec)
    if issues:
        print("[FAIL] Feature spec validation failed:")
        for issue in issues:
            print(" -", issue)
        return 1
    print("[OK] Feature spec validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
