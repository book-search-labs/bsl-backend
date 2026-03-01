#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _extract_scenarios(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("scenarios")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _scenario_ids(scenarios: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for scenario in scenarios:
        scenario_id = str(scenario.get("id") or "").strip()
        if scenario_id:
            ids.add(scenario_id)
    return ids


def _is_valid_scenario_stub(stub: Any) -> bool:
    if not isinstance(stub, dict):
        return False
    scenario_id = str(stub.get("id") or "").strip()
    turns = stub.get("turns")
    return bool(scenario_id and isinstance(turns, list) and len(turns) > 0)


def build_candidate_payload(
    seeds_payload: dict[str, Any],
    *,
    base_fixture: dict[str, Any],
) -> dict[str, Any]:
    base_scenarios = _extract_scenarios(base_fixture)
    existing_ids = _scenario_ids(base_scenarios)
    seed_items = seeds_payload.get("items") if isinstance(seeds_payload.get("items"), list) else []

    candidates: list[dict[str, Any]] = []
    accepted = 0
    skipped_existing = 0
    skipped_invalid = 0
    seen_ids: set[str] = set()

    for raw in seed_items:
        if not isinstance(raw, dict):
            skipped_invalid += 1
            continue
        stub = raw.get("scenario_stub")
        if not _is_valid_scenario_stub(stub):
            skipped_invalid += 1
            continue
        scenario = dict(stub)
        scenario_id = str(scenario.get("id") or "").strip()
        if scenario_id in existing_ids or scenario_id in seen_ids:
            skipped_existing += 1
            continue
        seen_ids.add(scenario_id)
        accepted += 1
        candidates.append(
            {
                "scenario_id": scenario_id,
                "reason_code": str(raw.get("reason_code") or "UNKNOWN"),
                "count": int(raw.get("count") or 0),
                "source_item_id": str(raw.get("id") or ""),
                "source_title": str(raw.get("title") or ""),
                "review_required": True,
                "scenario": scenario,
            }
        )

    return {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "base_scenario_count": len(base_scenarios),
            "seed_item_count": len([item for item in seed_items if isinstance(item, dict)]),
            "accepted_count": accepted,
            "skipped_existing_count": skipped_existing,
            "skipped_invalid_count": skipped_invalid,
        },
        "candidates": candidates,
    }


def render_markdown(payload: dict[str, Any], *, seed_source: str, base_fixture_source: str) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    lines: list[str] = []
    lines.append("# Chat Regression Fixture Candidates")
    lines.append("")
    lines.append(f"- generated_at: `{payload.get('generated_at')}`")
    lines.append(f"- seed_source: `{seed_source}`")
    lines.append(f"- base_fixture_source: `{base_fixture_source}`")
    lines.append(f"- base_scenario_count: {int(summary.get('base_scenario_count') or 0)}")
    lines.append(f"- seed_item_count: {int(summary.get('seed_item_count') or 0)}")
    lines.append(f"- accepted_count: {int(summary.get('accepted_count') or 0)}")
    lines.append(f"- skipped_existing_count: {int(summary.get('skipped_existing_count') or 0)}")
    lines.append(f"- skipped_invalid_count: {int(summary.get('skipped_invalid_count') or 0)}")
    lines.append("")
    if not candidates:
        lines.append("- no fixture candidates")
        return "\n".join(lines)
    for idx, item in enumerate(candidates, start=1):
        lines.append(f"## {idx}. {item.get('scenario_id')}")
        lines.append("")
        lines.append(f"- reason_code: `{item.get('reason_code')}`")
        lines.append(f"- feedback_count: {int(item.get('count') or 0)}")
        lines.append(f"- source_item_id: `{item.get('source_item_id')}`")
        lines.append("- review_required: `true`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(item.get("scenario"), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build regression fixture candidates from feedback seed payload.")
    parser.add_argument("--seeds-json", default="evaluation/chat/feedback_regression_seeds.json")
    parser.add_argument("--base-fixture", default="services/query-service/tests/fixtures/chat_state_regression_v1.json")
    parser.add_argument(
        "--output-json",
        default="evaluation/chat/feedback_regression_fixture_candidates.json",
    )
    parser.add_argument(
        "--output-md",
        default="tasks/backlog/generated/chat_feedback_regression_fixture_candidates.md",
    )
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    seeds_path = Path(args.seeds_json)
    seeds_payload = load_json(seeds_path)
    seed_items = seeds_payload.get("items") if isinstance(seeds_payload.get("items"), list) else []
    if not seed_items and not args.allow_empty:
        print("[FAIL] no seed items found")
        return 1

    base_fixture = load_json(Path(args.base_fixture))
    payload = build_candidate_payload(seeds_payload, base_fixture=base_fixture)

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote regression fixture candidate json -> {output_json}")

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(
        render_markdown(payload, seed_source=str(seeds_path), base_fixture_source=str(args.base_fixture)),
        encoding="utf-8",
    )
    print(f"[OK] wrote regression fixture candidate markdown -> {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
