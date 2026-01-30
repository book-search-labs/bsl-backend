import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "contracts"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"

SCHEMA_FILES = {
    "query-context.sample.json": CONTRACTS_DIR / "query-context.schema.json",
    "search-request.sample.json": CONTRACTS_DIR / "search-request.schema.json",
    "search-response.sample.json": CONTRACTS_DIR / "search-response.schema.json",
    "autocomplete-response.sample.json": CONTRACTS_DIR / "autocomplete-response.schema.json",
    "book-detail-response.sample.json": CONTRACTS_DIR / "book-detail-response.schema.json",
    "error.sample.json": CONTRACTS_DIR / "error.schema.json",
    "reindex-job-create-request.sample.json": CONTRACTS_DIR / "reindex-job-create-request.schema.json",
    "reindex-job-response.sample.json": CONTRACTS_DIR / "reindex-job-response.schema.json",
}

def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def validate(schema_path: Path, instance_path: Path) -> list[str]:
    schema = load_json(schema_path)
    instance = load_json(instance_path)

    # Resolve local refs like "query-context.schema.json"
    resolver = RefResolver(base_uri=schema_path.as_uri(), referrer=schema)
    validator = Draft202012Validator(schema, resolver=resolver)

    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    msgs = []
    for e in errors:
        path = ".".join(map(str, e.path)) or "<root>"
        msgs.append(f"{instance_path.name}: {path}: {e.message}")
    return msgs

def main() -> int:
    if not EXAMPLES_DIR.exists():
        print(f"[SKIP] examples dir not found: {EXAMPLES_DIR}")
        return 0

    all_errors: list[str] = []
    for example_name, schema_path in SCHEMA_FILES.items():
        inst_path = EXAMPLES_DIR / example_name
        if not schema_path.exists():
            all_errors.append(f"Missing schema: {schema_path}")
            continue
        if not inst_path.exists():
            all_errors.append(f"Missing example: {inst_path}")
            continue

        all_errors.extend(validate(schema_path, inst_path))

    if all_errors:
        print("[FAIL] Contract validation failed:")
        for msg in all_errors[:200]:
            print(" -", msg)
        if len(all_errors) > 200:
            print(f" ... and {len(all_errors) - 200} more")
        return 1

    print("[OK] All contract examples validate against schemas.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
