import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "contracts"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"

SCHEMA_FILES = {
    "query-context.sample.json": CONTRACTS_DIR / "query-context-v1_1.schema.json",
    "query-context-v1.sample.json": CONTRACTS_DIR / "query_context" / "v1" / "query-context.schema.json",
    "query-prepare-request.sample.json": CONTRACTS_DIR / "query-prepare-request.schema.json",
    "query-enhance-request.sample.json": CONTRACTS_DIR / "query-enhance-request.schema.json",
    "query-enhance-response.sample.json": CONTRACTS_DIR / "query-enhance-response.schema.json",
    "query-rewrite-failure-response.sample.json": CONTRACTS_DIR / "query-rewrite-failure-response.schema.json",
    "search-request.sample.json": CONTRACTS_DIR / "search-request.schema.json",
    "search-response.sample.json": CONTRACTS_DIR / "search-response.schema.json",
    "autocomplete-response.sample.json": CONTRACTS_DIR / "autocomplete-response.schema.json",
    "autocomplete-select-request.sample.json": CONTRACTS_DIR / "autocomplete-select-request.schema.json",
    "search-click-request.sample.json": CONTRACTS_DIR / "search-click-request.schema.json",
    "search-dwell-request.sample.json": CONTRACTS_DIR / "search-dwell-request.schema.json",
    "ack-response.sample.json": CONTRACTS_DIR / "ack-response.schema.json",
    "autocomplete-admin-suggestions-response.sample.json": CONTRACTS_DIR / "autocomplete-admin-suggestions-response.schema.json",
    "autocomplete-admin-update-request.sample.json": CONTRACTS_DIR / "autocomplete-admin-update-request.schema.json",
    "autocomplete-admin-update-response.sample.json": CONTRACTS_DIR / "autocomplete-admin-update-response.schema.json",
    "autocomplete-admin-trends-response.sample.json": CONTRACTS_DIR / "autocomplete-admin-trends-response.schema.json",
    "book-detail-response.sample.json": CONTRACTS_DIR / "book-detail-response.schema.json",
    "home-collections-response.sample.json": CONTRACTS_DIR / "home-collections-response.schema.json",
    "home-benefits-response.sample.json": CONTRACTS_DIR / "home-benefits-response.schema.json",
    "home-preorders-response.sample.json": CONTRACTS_DIR / "home-preorders-response.schema.json",
    "home-preorder-reserve-request.sample.json": CONTRACTS_DIR / "home-preorder-reserve-request.schema.json",
    "home-preorder-reserve-response.sample.json": CONTRACTS_DIR / "home-preorder-reserve-response.schema.json",
    "error.sample.json": CONTRACTS_DIR / "error.schema.json",
    "reindex-job-create-request.sample.json": CONTRACTS_DIR / "reindex-job-create-request.schema.json",
    "reindex-job-response.sample.json": CONTRACTS_DIR / "reindex-job-response.schema.json",
    "job-run-response.sample.json": CONTRACTS_DIR / "job-run-response.schema.json",
    "job-run-list-response.sample.json": CONTRACTS_DIR / "job-run-list-response.schema.json",
    "reindex-job-list-response.sample.json": CONTRACTS_DIR / "reindex-job-list-response.schema.json",
    "ops-task-list-response.sample.json": CONTRACTS_DIR / "ops-task-list-response.schema.json",
    "authority-merge-group-list-response.sample.json": CONTRACTS_DIR / "authority-merge-group-list-response.schema.json",
    "authority-merge-group-resolve-request.sample.json": CONTRACTS_DIR / "authority-merge-group-resolve-request.schema.json",
    "authority-merge-group-response.sample.json": CONTRACTS_DIR / "authority-merge-group-response.schema.json",
    "agent-alias-list-response.sample.json": CONTRACTS_DIR / "agent-alias-list-response.schema.json",
    "agent-alias-upsert-request.sample.json": CONTRACTS_DIR / "agent-alias-upsert-request.schema.json",
    "agent-alias-response.sample.json": CONTRACTS_DIR / "agent-alias-response.schema.json",
    "chat-provider-snapshot-response.sample.json": CONTRACTS_DIR / "chat-provider-snapshot-response.schema.json",
    "chat-session-state-response.sample.json": CONTRACTS_DIR / "chat-session-state-response.schema.json",
    "chat-session-reset-response.sample.json": CONTRACTS_DIR / "chat-session-reset-response.schema.json",
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
