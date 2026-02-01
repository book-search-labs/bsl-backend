import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "events"


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


def collect_schema_files() -> list[Path]:
    if not SCHEMA_DIR.exists():
        return []
    return [p for p in SCHEMA_DIR.glob("*.schema.json") if p.is_file()]


def main() -> int:
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "origin/develop"

    try:
        subprocess.check_output(["git", "rev-parse", base_ref], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"[SKIP] base ref not found: {base_ref}")
        return 0

    issues: list[str] = []
    for path in collect_schema_files():
        base_text = git_show(base_ref, path)
        head_text = path.read_text(encoding="utf-8")
        if base_text is None:
            continue
        base_schema = load_json(base_text)
        head_schema = load_json(head_text)
        check_schema(base_schema, head_schema, path.name, issues)

    if issues:
        print("[FAIL] Event schema compatibility check failed:")
        for issue in issues:
            print(" -", issue)
        return 1

    print("[OK] Event schema compatibility check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
