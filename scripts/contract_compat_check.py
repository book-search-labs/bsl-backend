import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "contracts"
OPENAPI_DIR = CONTRACTS_DIR / "openapi"


def git_show(ref: str, path: Path) -> str | None:
    rel = path.relative_to(ROOT)
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{rel.as_posix()}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None


def load_json(text: str) -> dict:
    return json.loads(text)


def load_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    return yaml.safe_load(text)


def schema_type(schema: dict) -> set[str]:
    t = schema.get("type")
    if isinstance(t, list):
        return set(t)
    if isinstance(t, str):
        return {t}
    return set()


def check_schema(base: dict, head: dict, path: str, issues: list[str]) -> None:
    base_types = schema_type(base)
    head_types = schema_type(head)
    if base_types and head_types and not base_types.issubset(head_types):
        issues.append(f"{path}: type changed from {sorted(base_types)} to {sorted(head_types)}")
        return

    base_enum = base.get("enum")
    head_enum = head.get("enum")
    if isinstance(base_enum, list) and isinstance(head_enum, list):
        if not set(base_enum).issubset(set(head_enum)):
            issues.append(f"{path}: enum shrink")

    base_required = set(base.get("required", [])) if isinstance(base.get("required"), list) else set()
    head_required = set(head.get("required", [])) if isinstance(head.get("required"), list) else set()
    if head_required - base_required:
        issues.append(f"{path}: new required fields {sorted(head_required - base_required)}")

    if base.get("additionalProperties") is True and head.get("additionalProperties") is False:
        issues.append(f"{path}: additionalProperties tightened")

    base_props = base.get("properties") if isinstance(base.get("properties"), dict) else None
    head_props = head.get("properties") if isinstance(head.get("properties"), dict) else None
    if base_props is not None:
        if head_props is None:
            issues.append(f"{path}: properties removed")
            return
        for prop, base_schema in base_props.items():
            if prop not in head_props:
                issues.append(f"{path}: property removed '{prop}'")
                continue
            check_schema(base_schema, head_props[prop], f"{path}.{prop}" if path else prop, issues)

    if "items" in base:
        if "items" not in head:
            issues.append(f"{path}: items removed")
        else:
            check_schema(base["items"], head["items"], f"{path}[]", issues)


def is_empty_schema(schema: dict) -> bool:
    meaningful_keys = {k for k in schema.keys() if k not in {"$schema", "$id", "title", "description"}}
    if not meaningful_keys:
        return True
    if "type" not in schema and "properties" not in schema and "required" not in schema and "enum" not in schema:
        return True
    return False


def check_openapi(base: dict, head: dict, issues: list[str]) -> None:
    base_paths = base.get("paths", {}) if isinstance(base.get("paths"), dict) else {}
    head_paths = head.get("paths", {}) if isinstance(head.get("paths"), dict) else {}
    for path, base_item in base_paths.items():
        if path not in head_paths:
            issues.append(f"openapi: removed path {path}")
            continue
        base_methods = set(k.lower() for k in base_item.keys() if isinstance(base_item, dict))
        head_methods = set(k.lower() for k in head_paths[path].keys() if isinstance(head_paths[path], dict))
        removed_methods = base_methods - head_methods
        for method in sorted(removed_methods):
            issues.append(f"openapi: removed operation {method.upper()} {path}")


def collect_contract_files() -> list[Path]:
    files = []
    files.extend(CONTRACTS_DIR.glob("*.schema.json"))
    files.extend((CONTRACTS_DIR / "jsonschema").glob("*.json"))
    files.extend((CONTRACTS_DIR / "query_context" / "v1").glob("*.json"))
    files.extend(OPENAPI_DIR.glob("*.yaml"))
    files.extend(OPENAPI_DIR.glob("*.yml"))
    files.extend(OPENAPI_DIR.glob("*.json"))
    return [f for f in files if f.is_file()]


def main() -> int:
    base_ref = sys.argv[1] if len(sys.argv) > 1 else None
    if not base_ref:
        base_ref = "origin/develop"

    try:
        subprocess.check_output(["git", "rev-parse", base_ref], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"[SKIP] base ref not found: {base_ref}")
        return 0

    issues: list[str] = []
    for path in collect_contract_files():
        base_text = git_show(base_ref, path)
        head_text = path.read_text(encoding="utf-8")
        if base_text is None:
            continue

        if path.suffix in {".yaml", ".yml", ".json"} and path.parent.name == "openapi":
            base_doc = load_yaml(base_text) if path.suffix in {".yaml", ".yml"} else load_json(base_text)
            head_doc = load_yaml(head_text) if path.suffix in {".yaml", ".yml"} else load_json(head_text)
            if base_doc is None or head_doc is None:
                print("[SKIP] YAML parser not available for openapi files")
                continue
            check_openapi(base_doc, head_doc, issues)
            continue

        if path.suffix == ".json":
            base_schema = load_json(base_text)
            head_schema = load_json(head_text)
            if is_empty_schema(base_schema):
                continue
            check_schema(base_schema, head_schema, path.name, issues)

    if issues:
        print("[FAIL] Contract compatibility check failed:")
        for issue in issues:
            print(" -", issue)
        return 1

    print("[OK] Contract compatibility check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
