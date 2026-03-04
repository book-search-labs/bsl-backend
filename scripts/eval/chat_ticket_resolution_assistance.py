#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


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


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
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


def _event_ts(row: Mapping[str, Any]) -> datetime | None:
    for key in ("timestamp", "event_time", "created_at", "updated_at", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _read_jsonl(path: Path, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, Mapping):
            rows.append({str(k): v for k, v in item.items()})
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    threshold = datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _event_ts(row)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _ticket_id(row: Mapping[str, Any]) -> str:
    return str(row.get("ticket_id") or row.get("id") or row.get("case_id") or "").strip()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    return []


def summarize_resolution_assistance(
    rows: list[Mapping[str, Any]],
    *,
    confidence_threshold: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    assistance_total = 0
    with_similar_case_total = 0
    with_template_total = 0
    with_question_total = 0
    insufficient_assistance_total = 0
    missing_reason_code_total = 0
    low_confidence_unrouted_total = 0

    for row in rows:
        if not _ticket_id(row):
            continue
        assistance_total += 1

        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        similar_cases = _as_list(row.get("similar_cases"))
        templates = _as_list(row.get("resolution_templates") or row.get("suggested_templates") or row.get("templates"))
        questions = _as_list(
            row.get("suggested_questions") or row.get("followup_questions") or row.get("clarification_questions")
        )
        reason_code = str(row.get("reason_code") or row.get("assist_reason_code") or "").strip()

        if similar_cases:
            with_similar_case_total += 1
        if templates:
            with_template_total += 1
        if questions:
            with_question_total += 1
        if not similar_cases and not templates and not questions:
            insufficient_assistance_total += 1
        if not reason_code:
            missing_reason_code_total += 1

        confidence = _safe_float(row.get("confidence"), 1.0)
        manual_review = _safe_bool(row.get("manual_review"), False)
        if confidence < float(confidence_threshold) and not manual_review:
            low_confidence_unrouted_total += 1

    similar_case_coverage_ratio = (
        1.0 if assistance_total == 0 else float(with_similar_case_total) / float(assistance_total)
    )
    template_coverage_ratio = 1.0 if assistance_total == 0 else float(with_template_total) / float(assistance_total)
    question_coverage_ratio = 1.0 if assistance_total == 0 else float(with_question_total) / float(assistance_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "assistance_total": assistance_total,
        "with_similar_case_total": with_similar_case_total,
        "with_template_total": with_template_total,
        "with_question_total": with_question_total,
        "similar_case_coverage_ratio": similar_case_coverage_ratio,
        "template_coverage_ratio": template_coverage_ratio,
        "question_coverage_ratio": question_coverage_ratio,
        "insufficient_assistance_total": insufficient_assistance_total,
        "missing_reason_code_total": missing_reason_code_total,
        "low_confidence_unrouted_total": low_confidence_unrouted_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_insufficient_assistance_total: int,
    min_similar_case_coverage_ratio: float,
    min_template_coverage_ratio: float,
    min_question_coverage_ratio: float,
    max_missing_reason_code_total: int,
    max_low_confidence_unrouted_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    insufficient_assistance_total = _safe_int(summary.get("insufficient_assistance_total"), 0)
    similar_case_coverage_ratio = _safe_float(summary.get("similar_case_coverage_ratio"), 1.0)
    template_coverage_ratio = _safe_float(summary.get("template_coverage_ratio"), 1.0)
    question_coverage_ratio = _safe_float(summary.get("question_coverage_ratio"), 1.0)
    missing_reason_code_total = _safe_int(summary.get("missing_reason_code_total"), 0)
    low_confidence_unrouted_total = _safe_int(summary.get("low_confidence_unrouted_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket resolution assistance window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if insufficient_assistance_total > max(0, int(max_insufficient_assistance_total)):
        failures.append(
            "ticket resolution assistance insufficient total exceeded: "
            f"{insufficient_assistance_total} > {int(max_insufficient_assistance_total)}"
        )
    if similar_case_coverage_ratio < max(0.0, float(min_similar_case_coverage_ratio)):
        failures.append(
            "ticket resolution assistance similar-case coverage below threshold: "
            f"{similar_case_coverage_ratio:.4f} < {float(min_similar_case_coverage_ratio):.4f}"
        )
    if template_coverage_ratio < max(0.0, float(min_template_coverage_ratio)):
        failures.append(
            "ticket resolution assistance template coverage below threshold: "
            f"{template_coverage_ratio:.4f} < {float(min_template_coverage_ratio):.4f}"
        )
    if question_coverage_ratio < max(0.0, float(min_question_coverage_ratio)):
        failures.append(
            "ticket resolution assistance question coverage below threshold: "
            f"{question_coverage_ratio:.4f} < {float(min_question_coverage_ratio):.4f}"
        )
    if missing_reason_code_total > max(0, int(max_missing_reason_code_total)):
        failures.append(
            f"ticket resolution assistance missing reason code total exceeded: {missing_reason_code_total} > {int(max_missing_reason_code_total)}"
        )
    if low_confidence_unrouted_total > max(0, int(max_low_confidence_unrouted_total)):
        failures.append(
            "ticket resolution assistance low-confidence unrouted total exceeded: "
            f"{low_confidence_unrouted_total} > {int(max_low_confidence_unrouted_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket resolution assistance stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_assistance_total_drop: int,
    max_insufficient_assistance_total_increase: int,
    max_similar_case_coverage_ratio_drop: float,
    max_template_coverage_ratio_drop: float,
    max_question_coverage_ratio_drop: float,
    max_missing_reason_code_total_increase: int,
    max_low_confidence_unrouted_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_assistance_total = _safe_int(base_summary.get("assistance_total"), 0)
    cur_assistance_total = _safe_int(current_summary.get("assistance_total"), 0)
    assistance_total_drop = max(0, base_assistance_total - cur_assistance_total)
    if assistance_total_drop > max(0, int(max_assistance_total_drop)):
        failures.append(
            "assistance_total regression: "
            f"baseline={base_assistance_total}, current={cur_assistance_total}, "
            f"allowed_drop={max(0, int(max_assistance_total_drop))}"
        )

    baseline_increase_pairs = [
        ("insufficient_assistance_total", max_insufficient_assistance_total_increase),
        ("missing_reason_code_total", max_missing_reason_code_total_increase),
        ("low_confidence_unrouted_total", max_low_confidence_unrouted_total_increase),
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

    baseline_ratio_drop_pairs = [
        ("similar_case_coverage_ratio", max_similar_case_coverage_ratio_drop),
        ("template_coverage_ratio", max_template_coverage_ratio_drop),
        ("question_coverage_ratio", max_question_coverage_ratio_drop),
    ]
    for key, allowed_drop in baseline_ratio_drop_pairs:
        base_value = _safe_float(base_summary.get(key), 0.0)
        cur_value = _safe_float(current_summary.get(key), 0.0)
        drop = max(0.0, base_value - cur_value)
        if drop > max(0.0, float(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value:.6f}, current={cur_value:.6f}, "
                f"allowed_drop={float(allowed_drop):.6f}"
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
    lines.append("# Chat Ticket Resolution Assistance")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- assistance_jsonl: {payload.get('assistance_jsonl')}")
    lines.append(f"- assistance_total: {_safe_int(summary.get('assistance_total'), 0)}")
    lines.append(f"- similar_case_coverage_ratio: {_safe_float(summary.get('similar_case_coverage_ratio'), 1.0):.4f}")
    lines.append(f"- template_coverage_ratio: {_safe_float(summary.get('template_coverage_ratio'), 1.0):.4f}")
    lines.append(f"- question_coverage_ratio: {_safe_float(summary.get('question_coverage_ratio'), 1.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat ticket resolution assistance quality.")
    parser.add_argument("--assistance-jsonl", default="var/chat_ticket/resolution_assistance.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--confidence-threshold", type=float, default=0.6)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_resolution_assistance")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-insufficient-assistance-total", type=int, default=0)
    parser.add_argument("--min-similar-case-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-template-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-question-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-reason-code-total", type=int, default=0)
    parser.add_argument("--max-low-confidence-unrouted-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-assistance-total-drop", type=int, default=10)
    parser.add_argument("--max-insufficient-assistance-total-increase", type=int, default=0)
    parser.add_argument("--max-similar-case-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-template-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-question-coverage-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-missing-reason-code-total-increase", type=int, default=0)
    parser.add_argument("--max-low-confidence-unrouted-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.assistance_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_resolution_assistance(
        rows,
        confidence_threshold=max(0.0, float(args.confidence_threshold)),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_insufficient_assistance_total=max(0, int(args.max_insufficient_assistance_total)),
        min_similar_case_coverage_ratio=max(0.0, float(args.min_similar_case_coverage_ratio)),
        min_template_coverage_ratio=max(0.0, float(args.min_template_coverage_ratio)),
        min_question_coverage_ratio=max(0.0, float(args.min_question_coverage_ratio)),
        max_missing_reason_code_total=max(0, int(args.max_missing_reason_code_total)),
        max_low_confidence_unrouted_total=max(0, int(args.max_low_confidence_unrouted_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_assistance_total_drop=max(0, int(args.max_assistance_total_drop)),
            max_insufficient_assistance_total_increase=max(0, int(args.max_insufficient_assistance_total_increase)),
            max_similar_case_coverage_ratio_drop=max(0.0, float(args.max_similar_case_coverage_ratio_drop)),
            max_template_coverage_ratio_drop=max(0.0, float(args.max_template_coverage_ratio_drop)),
            max_question_coverage_ratio_drop=max(0.0, float(args.max_question_coverage_ratio_drop)),
            max_missing_reason_code_total_increase=max(0, int(args.max_missing_reason_code_total_increase)),
            max_low_confidence_unrouted_total_increase=max(0, int(args.max_low_confidence_unrouted_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assistance_jsonl": str(args.assistance_jsonl),
        "source": {
            "assistance_jsonl": str(args.assistance_jsonl),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
            "confidence_threshold": float(args.confidence_threshold),
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
                "min_window": int(args.min_window),
                "confidence_threshold": float(args.confidence_threshold),
                "max_insufficient_assistance_total": int(args.max_insufficient_assistance_total),
                "min_similar_case_coverage_ratio": float(args.min_similar_case_coverage_ratio),
                "min_template_coverage_ratio": float(args.min_template_coverage_ratio),
                "min_question_coverage_ratio": float(args.min_question_coverage_ratio),
                "max_missing_reason_code_total": int(args.max_missing_reason_code_total),
                "max_low_confidence_unrouted_total": int(args.max_low_confidence_unrouted_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_assistance_total_drop": int(args.max_assistance_total_drop),
                "max_insufficient_assistance_total_increase": int(args.max_insufficient_assistance_total_increase),
                "max_similar_case_coverage_ratio_drop": float(args.max_similar_case_coverage_ratio_drop),
                "max_template_coverage_ratio_drop": float(args.max_template_coverage_ratio_drop),
                "max_question_coverage_ratio_drop": float(args.max_question_coverage_ratio_drop),
                "max_missing_reason_code_total_increase": int(args.max_missing_reason_code_total_increase),
                "max_low_confidence_unrouted_total_increase": int(args.max_low_confidence_unrouted_total_increase),
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
    print(f"assistance_total={_safe_int(summary.get('assistance_total'), 0)}")
    print(f"insufficient_assistance_total={_safe_int(summary.get('insufficient_assistance_total'), 0)}")
    print(f"similar_case_coverage_ratio={_safe_float(summary.get('similar_case_coverage_ratio'), 1.0):.4f}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
