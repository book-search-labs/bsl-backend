#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REQUIRED_CATEGORIES_DEFAULT = {"ORDER", "PAYMENT", "SHIPPING", "REFUND", "ACCOUNT", "OTHER"}
REQUIRED_SEVERITIES_DEFAULT = {"S1", "S2", "S3", "S4"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, Mapping):
        return {str(k): v for k, v in payload.items()}
    return {}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _collect_codes(value: Any) -> tuple[list[str], int]:
    codes: list[str] = []
    duplicate_total = 0
    seen: set[str] = set()

    if isinstance(value, Mapping):
        entries = value.values()
    elif isinstance(value, list):
        entries = value
    else:
        entries = []

    for item in entries:
        code = ""
        if isinstance(item, Mapping):
            code = _normalize_code(item.get("code") or item.get("id") or item.get("name") or item.get("key"))
        else:
            code = _normalize_code(item)
        if not code:
            continue
        if code in seen:
            duplicate_total += 1
            continue
        seen.add(code)
        codes.append(code)
    return codes, duplicate_total


def _taxonomy_items(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                rows.append({str(k): v for k, v in item.items()})
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, Mapping):
                row = {str(k): v for k, v in item.items()}
                row.setdefault("code", key)
                rows.append(row)
            else:
                rows.append({"code": str(key), "value": item})
    return rows


def summarize_triage_taxonomy(
    payload: Mapping[str, Any],
    *,
    required_categories: set[str],
    required_severities: set[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    version = str(payload.get("version") or payload.get("taxonomy_version") or "").strip()
    updated_at = _parse_ts(payload.get("updated_at") or payload.get("generated_at") or payload.get("timestamp"))
    stale_minutes = 999999.0 if updated_at is None else max(0.0, (now_dt - updated_at).total_seconds() / 60.0)

    categories, duplicate_category_total = _collect_codes(payload.get("categories"))
    severities, duplicate_severity_total = _collect_codes(payload.get("severities"))

    missing_categories = sorted(required_categories - set(categories))
    missing_severities = sorted(required_severities - set(severities))

    missing_severity_rule_total = 0
    for row in _taxonomy_items(payload.get("categories")):
        severity_rules = row.get("severity_rules") or row.get("severity_criteria") or row.get("allowed_severities")
        if severity_rules is None:
            missing_severity_rule_total += 1
            continue
        if isinstance(severity_rules, list) and len(severity_rules) == 0:
            missing_severity_rule_total += 1
            continue
        if isinstance(severity_rules, Mapping) and len(severity_rules) == 0:
            missing_severity_rule_total += 1

    return {
        "taxonomy_version": version,
        "version_missing": len(version) == 0,
        "category_total": len(categories),
        "severity_total": len(severities),
        "duplicate_category_total": duplicate_category_total,
        "duplicate_severity_total": duplicate_severity_total,
        "missing_categories": missing_categories,
        "missing_severities": missing_severities,
        "missing_category_total": len(missing_categories),
        "missing_severity_total": len(missing_severities),
        "missing_severity_rule_total": missing_severity_rule_total,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_category_total: int,
    min_severity_total: int,
    require_taxonomy_version: bool,
    max_missing_category_total: int,
    max_missing_severity_total: int,
    max_duplicate_category_total: int,
    max_duplicate_severity_total: int,
    max_missing_severity_rule_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    category_total = _safe_int(summary.get("category_total"), 0)
    severity_total = _safe_int(summary.get("severity_total"), 0)
    version_missing = bool(summary.get("version_missing"))
    missing_category_total = _safe_int(summary.get("missing_category_total"), 0)
    missing_severity_total = _safe_int(summary.get("missing_severity_total"), 0)
    duplicate_category_total = _safe_int(summary.get("duplicate_category_total"), 0)
    duplicate_severity_total = _safe_int(summary.get("duplicate_severity_total"), 0)
    missing_severity_rule_total = _safe_int(summary.get("missing_severity_rule_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if category_total < max(0, int(min_category_total)):
        failures.append(f"ticket triage category total too small: {category_total} < {int(min_category_total)}")
    if severity_total < max(0, int(min_severity_total)):
        failures.append(f"ticket triage severity total too small: {severity_total} < {int(min_severity_total)}")
    if require_taxonomy_version and version_missing:
        failures.append("ticket triage taxonomy version is required")
    if missing_category_total > max(0, int(max_missing_category_total)):
        failures.append(
            f"ticket triage missing category total exceeded: {missing_category_total} > {int(max_missing_category_total)}"
        )
    if missing_severity_total > max(0, int(max_missing_severity_total)):
        failures.append(
            f"ticket triage missing severity total exceeded: {missing_severity_total} > {int(max_missing_severity_total)}"
        )
    if duplicate_category_total > max(0, int(max_duplicate_category_total)):
        failures.append(
            f"ticket triage duplicate category total exceeded: {duplicate_category_total} > {int(max_duplicate_category_total)}"
        )
    if duplicate_severity_total > max(0, int(max_duplicate_severity_total)):
        failures.append(
            f"ticket triage duplicate severity total exceeded: {duplicate_severity_total} > {int(max_duplicate_severity_total)}"
        )
    if missing_severity_rule_total > max(0, int(max_missing_severity_rule_total)):
        failures.append(
            "ticket triage missing severity rule total exceeded: "
            f"{missing_severity_rule_total} > {int(max_missing_severity_rule_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket triage taxonomy stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_category_total_drop: int,
    max_severity_total_drop: int,
    max_version_missing_total_increase: int,
    max_missing_category_total_increase: int,
    max_missing_severity_total_increase: int,
    max_duplicate_category_total_increase: int,
    max_duplicate_severity_total_increase: int,
    max_missing_severity_rule_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("category_total", max_category_total_drop),
        ("severity_total", max_severity_total_drop),
    ]
    for key, allowed_drop in baseline_drop_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        drop = max(0, base_value - cur_value)
        if drop > max(0, int(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_drop={max(0, int(allowed_drop))}"
            )

    base_version_missing_total = 1 if bool(base_summary.get("version_missing")) else 0
    cur_version_missing_total = 1 if bool(current_summary.get("version_missing")) else 0
    version_missing_total_increase = max(0, cur_version_missing_total - base_version_missing_total)
    if version_missing_total_increase > max(0, int(max_version_missing_total_increase)):
        failures.append(
            "version_missing regression: "
            f"baseline={base_version_missing_total}, current={cur_version_missing_total}, "
            f"allowed_increase={max(0, int(max_version_missing_total_increase))}"
        )

    baseline_increase_pairs = [
        ("missing_category_total", max_missing_category_total_increase),
        ("missing_severity_total", max_missing_severity_total_increase),
        ("duplicate_category_total", max_duplicate_category_total_increase),
        ("duplicate_severity_total", max_duplicate_severity_total_increase),
        ("missing_severity_rule_total", max_missing_severity_rule_total_increase),
    ]
    for key, allowed_increase in baseline_increase_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        increase = max(0, cur_value - base_value)
        if increase > max(0, int(allowed_increase)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_increase={max(0, int(allowed_increase))}"
            )

    base_stale_minutes = _safe_float(base_summary.get("stale_minutes"), 0.0)
    cur_stale_minutes = _safe_float(current_summary.get("stale_minutes"), 0.0)
    stale_minutes_increase = max(0.0, cur_stale_minutes - base_stale_minutes)
    if stale_minutes_increase > max(0.0, float(max_stale_minutes_increase)):
        failures.append(
            "stale minutes regression: "
            f"baseline={base_stale_minutes:.6f}, current={cur_stale_minutes:.6f}, "
            f"allowed_increase={float(max_stale_minutes_increase):.6f}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Ticket Triage Taxonomy")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- taxonomy_json: {payload.get('taxonomy_json')}")
    lines.append(f"- category_total: {_safe_int(summary.get('category_total'), 0)}")
    lines.append(f"- severity_total: {_safe_int(summary.get('severity_total'), 0)}")
    lines.append(f"- missing_category_total: {_safe_int(summary.get('missing_category_total'), 0)}")
    lines.append(f"- missing_severity_total: {_safe_int(summary.get('missing_severity_total'), 0)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    if baseline_failures:
        for failure in baseline_failures:
            lines.append(f"- baseline_failure: {failure}")
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint triage taxonomy and severity criteria.")
    parser.add_argument("--taxonomy-json", default="var/chat_ticket/triage_taxonomy.json")
    parser.add_argument("--required-categories", default="ORDER,PAYMENT,SHIPPING,REFUND,ACCOUNT,OTHER")
    parser.add_argument("--required-severities", default="S1,S2,S3,S4")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_triage_taxonomy")
    parser.add_argument("--min-category-total", type=int, default=0)
    parser.add_argument("--min-severity-total", type=int, default=0)
    parser.add_argument("--require-taxonomy-version", action="store_true")
    parser.add_argument("--max-missing-category-total", type=int, default=0)
    parser.add_argument("--max-missing-severity-total", type=int, default=0)
    parser.add_argument("--max-duplicate-category-total", type=int, default=0)
    parser.add_argument("--max-duplicate-severity-total", type=int, default=0)
    parser.add_argument("--max-missing-severity-rule-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-category-total-drop", type=int, default=2)
    parser.add_argument("--max-severity-total-drop", type=int, default=1)
    parser.add_argument("--max-version-missing-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-category-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-severity-total-increase", type=int, default=0)
    parser.add_argument("--max-duplicate-category-total-increase", type=int, default=0)
    parser.add_argument("--max-duplicate-severity-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-severity-rule-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    taxonomy_path = Path(args.taxonomy_json)
    payload = _read_json(taxonomy_path)
    required_categories = {
        token.strip().upper() for token in str(args.required_categories).split(",") if token.strip()
    } or set(REQUIRED_CATEGORIES_DEFAULT)
    required_severities = {
        token.strip().upper() for token in str(args.required_severities).split(",") if token.strip()
    } or set(REQUIRED_SEVERITIES_DEFAULT)
    summary = summarize_triage_taxonomy(
        payload,
        required_categories=required_categories,
        required_severities=required_severities,
    )
    failures = evaluate_gate(
        summary,
        min_category_total=max(0, int(args.min_category_total)),
        min_severity_total=max(0, int(args.min_severity_total)),
        require_taxonomy_version=bool(args.require_taxonomy_version),
        max_missing_category_total=max(0, int(args.max_missing_category_total)),
        max_missing_severity_total=max(0, int(args.max_missing_severity_total)),
        max_duplicate_category_total=max(0, int(args.max_duplicate_category_total)),
        max_duplicate_severity_total=max(0, int(args.max_duplicate_severity_total)),
        max_missing_severity_rule_total=max(0, int(args.max_missing_severity_rule_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_category_total_drop=max(0, int(args.max_category_total_drop)),
            max_severity_total_drop=max(0, int(args.max_severity_total_drop)),
            max_version_missing_total_increase=max(0, int(args.max_version_missing_total_increase)),
            max_missing_category_total_increase=max(0, int(args.max_missing_category_total_increase)),
            max_missing_severity_total_increase=max(0, int(args.max_missing_severity_total_increase)),
            max_duplicate_category_total_increase=max(0, int(args.max_duplicate_category_total_increase)),
            max_duplicate_severity_total_increase=max(0, int(args.max_duplicate_severity_total_increase)),
            max_missing_severity_rule_total_increase=max(0, int(args.max_missing_severity_rule_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy_json": str(taxonomy_path),
        "source": {
            "taxonomy_json": str(taxonomy_path),
            "required_categories": sorted(required_categories),
            "required_severities": sorted(required_severities),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_category_total": int(args.min_category_total),
                "min_severity_total": int(args.min_severity_total),
                "require_taxonomy_version": bool(args.require_taxonomy_version),
                "max_missing_category_total": int(args.max_missing_category_total),
                "max_missing_severity_total": int(args.max_missing_severity_total),
                "max_duplicate_category_total": int(args.max_duplicate_category_total),
                "max_duplicate_severity_total": int(args.max_duplicate_severity_total),
                "max_missing_severity_rule_total": int(args.max_missing_severity_rule_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_category_total_drop": int(args.max_category_total_drop),
                "max_severity_total_drop": int(args.max_severity_total_drop),
                "max_version_missing_total_increase": int(args.max_version_missing_total_increase),
                "max_missing_category_total_increase": int(args.max_missing_category_total_increase),
                "max_missing_severity_total_increase": int(args.max_missing_severity_total_increase),
                "max_duplicate_category_total_increase": int(args.max_duplicate_category_total_increase),
                "max_duplicate_severity_total_increase": int(args.max_duplicate_severity_total_increase),
                "max_missing_severity_rule_total_increase": int(args.max_missing_severity_rule_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"category_total={_safe_int(summary.get('category_total'), 0)}")
    print(f"severity_total={_safe_int(summary.get('severity_total'), 0)}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
