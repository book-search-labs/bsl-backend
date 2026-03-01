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


def _scenario_id_set(scenarios: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("id") or "").strip() for item in scenarios if str(item.get("id") or "").strip()}


def _is_valid_scenario(scenario: Any) -> bool:
    if not isinstance(scenario, dict):
        return False
    scenario_id = str(scenario.get("id") or "").strip()
    turns = scenario.get("turns")
    return bool(scenario_id and isinstance(turns, list) and len(turns) > 0)


def apply_candidates(
    fixture_payload: dict[str, Any],
    candidates_payload: dict[str, Any],
    *,
    selected_ids: set[str] | None = None,
    max_add: int,
    allow_review_required: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    existing = _extract_scenarios(fixture_payload)
    existing_ids = _scenario_id_set(existing)
    candidates = candidates_payload.get("candidates") if isinstance(candidates_payload.get("candidates"), list) else []

    next_scenarios = list(existing)
    added_items: list[dict[str, Any]] = []
    skipped_existing: list[str] = []
    skipped_invalid: list[str] = []
    skipped_review: list[str] = []
    skipped_not_selected: list[str] = []

    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        scenario_id = str(raw.get("scenario_id") or "").strip()
        if not scenario_id:
            skipped_invalid.append("(missing_id)")
            continue
        if selected_ids and scenario_id not in selected_ids:
            skipped_not_selected.append(scenario_id)
            continue
        if scenario_id in existing_ids:
            skipped_existing.append(scenario_id)
            continue
        if bool(raw.get("review_required")) and not allow_review_required:
            skipped_review.append(scenario_id)
            continue
        scenario = raw.get("scenario")
        if not _is_valid_scenario(scenario):
            skipped_invalid.append(scenario_id)
            continue
        if max_add > 0 and len(added_items) >= max_add:
            skipped_not_selected.append(scenario_id)
            continue
        normalized = dict(scenario)
        normalized["id"] = scenario_id
        next_scenarios.append(normalized)
        existing_ids.add(scenario_id)
        added_items.append(
            {
                "scenario_id": scenario_id,
                "reason_code": str(raw.get("reason_code") or "UNKNOWN"),
                "count": int(raw.get("count") or 0),
                "source_item_id": str(raw.get("source_item_id") or ""),
            }
        )

    updated_payload = dict(fixture_payload)
    updated_payload["scenarios"] = next_scenarios
    report = {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_scenario_count": len(existing),
        "final_scenario_count": len(next_scenarios),
        "added_count": len(added_items),
        "added_items": added_items,
        "skipped_existing_count": len(skipped_existing),
        "skipped_existing": skipped_existing,
        "skipped_invalid_count": len(skipped_invalid),
        "skipped_invalid": skipped_invalid,
        "skipped_review_count": len(skipped_review),
        "skipped_review": skipped_review,
        "skipped_not_selected_count": len(skipped_not_selected),
        "skipped_not_selected": skipped_not_selected,
        "allow_review_required": bool(allow_review_required),
        "max_add": max_add,
        "selected_ids": sorted(selected_ids) if selected_ids else [],
    }
    return updated_payload, report


def render_report_markdown(report: dict[str, Any], *, fixture_path: str, candidates_path: str, dry_run: bool) -> str:
    lines: list[str] = []
    lines.append("# Chat Regression Fixture Apply Report")
    lines.append("")
    lines.append(f"- generated_at: `{report.get('generated_at')}`")
    lines.append(f"- fixture: `{fixture_path}`")
    lines.append(f"- candidates: `{candidates_path}`")
    lines.append(f"- dry_run: `{str(bool(dry_run)).lower()}`")
    lines.append(f"- base_scenario_count: {int(report.get('base_scenario_count') or 0)}")
    lines.append(f"- final_scenario_count: {int(report.get('final_scenario_count') or 0)}")
    lines.append(f"- added_count: {int(report.get('added_count') or 0)}")
    lines.append(f"- skipped_existing_count: {int(report.get('skipped_existing_count') or 0)}")
    lines.append(f"- skipped_invalid_count: {int(report.get('skipped_invalid_count') or 0)}")
    lines.append(f"- skipped_review_count: {int(report.get('skipped_review_count') or 0)}")
    lines.append(f"- skipped_not_selected_count: {int(report.get('skipped_not_selected_count') or 0)}")
    lines.append("")
    added = report.get("added_items") if isinstance(report.get("added_items"), list) else []
    if added:
        lines.append("## Added Items")
        lines.append("")
        for item in added:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                f"`{item.get('scenario_id')}` "
                f"(reason={item.get('reason_code')}, count={int(item.get('count') or 0)}, source={item.get('source_item_id')})"
            )
        lines.append("")
    else:
        lines.append("- no scenarios added")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply regression fixture candidates to chat regression fixture.")
    parser.add_argument("--fixture", default="services/query-service/tests/fixtures/chat_state_regression_v1.json")
    parser.add_argument("--candidates-json", default="evaluation/chat/feedback_regression_fixture_candidates.json")
    parser.add_argument("--output-fixture", default="")
    parser.add_argument("--report-json", default="evaluation/chat/feedback_regression_fixture_apply_report.json")
    parser.add_argument("--report-md", default="tasks/backlog/generated/chat_feedback_regression_fixture_apply_report.md")
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--max-add", type=int, default=0)
    parser.add_argument("--allow-review-required", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    candidates_path = Path(args.candidates_json)
    fixture_payload = load_json(fixture_path)
    candidates_payload = load_json(candidates_path)
    candidates = candidates_payload.get("candidates") if isinstance(candidates_payload.get("candidates"), list) else []
    if not candidates and not args.allow_empty:
        print("[FAIL] no candidates found")
        return 1

    selected_ids = {str(item).strip() for item in list(args.scenario_id or []) if str(item).strip()}
    updated, report = apply_candidates(
        fixture_payload,
        candidates_payload,
        selected_ids=selected_ids or None,
        max_add=max(0, int(args.max_add)),
        allow_review_required=bool(args.allow_review_required),
    )

    report_json_path = Path(args.report_json)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote apply report json -> {report_json_path}")

    report_md_path = Path(args.report_md)
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.write_text(
        render_report_markdown(report, fixture_path=str(fixture_path), candidates_path=str(candidates_path), dry_run=bool(args.dry_run)),
        encoding="utf-8",
    )
    print(f"[OK] wrote apply report markdown -> {report_md_path}")

    if args.dry_run:
        print("[OK] dry-run enabled; fixture not modified")
        return 0

    output_fixture = Path(args.output_fixture) if str(args.output_fixture).strip() else fixture_path
    output_fixture.parent.mkdir(parents=True, exist_ok=True)
    output_fixture.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote updated fixture -> {output_fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
