#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
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


def resolve_reports(reports_dir: Path, *, prefix: str, limit: int) -> list[Path]:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def _extract_unit_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    generated_at = str(payload.get("generated_at") or "")
    return {
        "generated_at": generated_at,
        "cost_per_resolved_session": _safe_float(summary.get("cost_per_resolved_session"), 0.0),
        "resolution_rate": _safe_float(summary.get("resolution_rate"), 0.0),
        "unresolved_cost_burn_total": _safe_float(summary.get("unresolved_cost_burn_total"), 0.0),
        "total_cost_usd": _safe_float(summary.get("total_cost_usd"), 0.0),
    }


def _extract_budget_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
    generated_at = str(payload.get("generated_at") or "")
    return {
        "generated_at": generated_at,
        "post_optimizer_budget_utilization": _safe_float(summary.get("post_optimizer_budget_utilization"), 0.0),
        "optimizer_mode": str(summary.get("optimizer_mode") or "NORMAL").strip().upper() or "NORMAL",
        "release_state": str(decision.get("release_state") or "UNKNOWN").strip().upper() or "UNKNOWN",
    }


def read_audit_rows(path: Path, *, window_days: int, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)

    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    threshold = (now or datetime.now(timezone.utc)) - timedelta(days=max(1, int(window_days)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _parse_ts(row.get("timestamp") or row.get("event_time") or row.get("ts"))
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def summarize_audit_reasons(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_reason: dict[str, dict[str, float]] = {}
    total_cost = 0.0
    total_tokens = 0

    for row in rows:
        reason = str(row.get("reason_code") or "NONE").strip().upper() or "NONE"
        cost = max(0.0, _safe_float(row.get("cost_usd"), 0.0))
        tokens = max(0, _safe_int(row.get("tokens"), 0))
        total_cost += cost
        total_tokens += tokens

        item = by_reason.setdefault(reason, {"count": 0.0, "cost_usd": 0.0, "tokens": 0.0})
        item["count"] += 1.0
        item["cost_usd"] += cost
        item["tokens"] += float(tokens)

    reason_rows = [
        {
            "reason_code": reason,
            "count": int(values["count"]),
            "cost_usd": float(values["cost_usd"]),
            "tokens": int(values["tokens"]),
            "cost_share": 0.0 if total_cost <= 0.0 else float(values["cost_usd"]) / total_cost,
        }
        for reason, values in sorted(by_reason.items(), key=lambda item: item[1]["cost_usd"], reverse=True)
    ]

    return {
        "window_size": len(rows),
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "top_reasons": reason_rows[:10],
    }


def build_tradeoff_summary(
    unit_rows: list[Mapping[str, Any]],
    budget_rows: list[Mapping[str, Any]],
    audit_summary: Mapping[str, Any],
) -> dict[str, Any]:
    unit_count = len(unit_rows)
    budget_count = len(budget_rows)

    avg_cost_per_resolved = 0.0
    avg_resolution_rate = 0.0
    avg_unresolved_burn = 0.0
    total_cost_usd = 0.0
    if unit_count > 0:
        avg_cost_per_resolved = sum(_safe_float(row.get("cost_per_resolved_session"), 0.0) for row in unit_rows) / float(unit_count)
        avg_resolution_rate = sum(_safe_float(row.get("resolution_rate"), 0.0) for row in unit_rows) / float(unit_count)
        avg_unresolved_burn = sum(_safe_float(row.get("unresolved_cost_burn_total"), 0.0) for row in unit_rows) / float(unit_count)
        total_cost_usd = sum(_safe_float(row.get("total_cost_usd"), 0.0) for row in unit_rows)

    avg_budget_utilization = 0.0
    mode_counts: dict[str, int] = {}
    release_state_counts: dict[str, int] = {}
    if budget_count > 0:
        avg_budget_utilization = (
            sum(_safe_float(row.get("post_optimizer_budget_utilization"), 0.0) for row in budget_rows) / float(budget_count)
        )
        for row in budget_rows:
            mode = str(row.get("optimizer_mode") or "NORMAL").strip().upper() or "NORMAL"
            state = str(row.get("release_state") or "UNKNOWN").strip().upper() or "UNKNOWN"
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            release_state_counts[state] = release_state_counts.get(state, 0) + 1

    tradeoff_index = avg_resolution_rate / (1.0 + avg_cost_per_resolved)

    first = unit_rows[0] if unit_rows else {}
    last = unit_rows[-1] if unit_rows else {}
    cost_delta = _safe_float(last.get("cost_per_resolved_session"), 0.0) - _safe_float(first.get("cost_per_resolved_session"), 0.0)
    resolution_delta = _safe_float(last.get("resolution_rate"), 0.0) - _safe_float(first.get("resolution_rate"), 0.0)
    quality_drop_with_cost_cut = cost_delta < 0.0 and resolution_delta < 0.0

    return {
        "report_count": unit_count,
        "budget_report_count": budget_count,
        "avg_cost_per_resolved_session": avg_cost_per_resolved,
        "avg_resolution_rate": avg_resolution_rate,
        "avg_unresolved_cost_burn_total": avg_unresolved_burn,
        "avg_budget_utilization": avg_budget_utilization,
        "total_cost_usd": total_cost_usd,
        "tradeoff_index": tradeoff_index,
        "cost_delta": cost_delta,
        "resolution_delta": resolution_delta,
        "quality_drop_with_cost_cut": quality_drop_with_cost_cut,
        "optimizer_mode_counts": mode_counts,
        "release_state_counts": release_state_counts,
        "audit_reason_top": audit_summary.get("top_reasons") if isinstance(audit_summary.get("top_reasons"), list) else [],
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_reports: int,
    min_tradeoff_index: float,
    max_avg_cost_per_resolved_session: float,
    max_avg_unresolved_cost_burn_total: float,
) -> list[str]:
    failures: list[str] = []
    report_count = _safe_int(summary.get("report_count"), 0)
    tradeoff_index = _safe_float(summary.get("tradeoff_index"), 0.0)
    avg_cost_per_resolved = _safe_float(summary.get("avg_cost_per_resolved_session"), 0.0)
    avg_unresolved_burn = _safe_float(summary.get("avg_unresolved_cost_burn_total"), 0.0)
    quality_drop_with_cost_cut = bool(summary.get("quality_drop_with_cost_cut"))

    if report_count < max(0, int(min_reports)):
        failures.append(f"finops report window too small: {report_count} < {int(min_reports)}")
    if report_count == 0:
        return failures

    if tradeoff_index < max(0.0, float(min_tradeoff_index)):
        failures.append(f"tradeoff index below threshold: {tradeoff_index:.4f} < {float(min_tradeoff_index):.4f}")
    if avg_cost_per_resolved > max(0.0, float(max_avg_cost_per_resolved_session)):
        failures.append(
            f"avg cost per resolved exceeded: {avg_cost_per_resolved:.4f} > {float(max_avg_cost_per_resolved_session):.4f}"
        )
    if avg_unresolved_burn > max(0.0, float(max_avg_unresolved_cost_burn_total)):
        failures.append(
            f"avg unresolved burn exceeded: {avg_unresolved_burn:.4f} > {float(max_avg_unresolved_cost_burn_total):.4f}"
        )
    if quality_drop_with_cost_cut:
        failures.append("quality dropped while cost was reduced (cost/quality tradeoff regression)")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat FinOps Tradeoff Report")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- report_count: {_safe_int(summary.get('report_count'), 0)}")
    lines.append(f"- avg_cost_per_resolved_session: {_safe_float(summary.get('avg_cost_per_resolved_session'), 0.0):.4f}")
    lines.append(f"- avg_resolution_rate: {_safe_float(summary.get('avg_resolution_rate'), 0.0):.4f}")
    lines.append(f"- avg_unresolved_cost_burn_total: {_safe_float(summary.get('avg_unresolved_cost_burn_total'), 0.0):.4f}")
    lines.append(f"- avg_budget_utilization: {_safe_float(summary.get('avg_budget_utilization'), 0.0):.4f}")
    lines.append(f"- tradeoff_index: {_safe_float(summary.get('tradeoff_index'), 0.0):.4f}")
    lines.append(f"- quality_drop_with_cost_cut: {str(bool(summary.get('quality_drop_with_cost_cut'))).lower()}")
    lines.append("")
    lines.append("## Top Reasons")
    lines.append("")
    reasons = summary.get("audit_reason_top") if isinstance(summary.get("audit_reason_top"), list) else []
    if not reasons:
        lines.append("- (none)")
    else:
        for row in reasons[:5]:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "- "
                f"{row.get('reason_code')}: count={_safe_int(row.get('count'), 0)} "
                f"cost_usd={_safe_float(row.get('cost_usd'), 0.0):.4f} "
                f"cost_share={_safe_float(row.get('cost_share'), 0.0):.4f}"
            )

    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- enabled: {str(bool(gate.get('enabled'))).lower()}")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    if failures:
        for failure in failures:
            lines.append(f"- failure: {failure}")
    else:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create weekly FinOps cost/quality tradeoff report from chat eval outputs.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--unit-prefix", default="chat_unit_economics_slo")
    parser.add_argument("--budget-prefix", default="chat_budget_release_guard")
    parser.add_argument("--report-limit", type=int, default=30)
    parser.add_argument("--llm-audit-log", default="var/llm_gateway/audit.log")
    parser.add_argument("--audit-window-days", type=int, default=7)
    parser.add_argument("--audit-limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_finops_tradeoff_report")
    parser.add_argument("--min-reports", type=int, default=1)
    parser.add_argument("--min-tradeoff-index", type=float, default=0.20)
    parser.add_argument("--max-avg-cost-per-resolved-session", type=float, default=2.5)
    parser.add_argument("--max-avg-unresolved-cost-burn-total", type=float, default=200.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)

    unit_reports = resolve_reports(
        reports_dir,
        prefix=str(args.unit_prefix),
        limit=max(1, int(args.report_limit)),
    )
    budget_reports = resolve_reports(
        reports_dir,
        prefix=str(args.budget_prefix),
        limit=max(1, int(args.report_limit)),
    )

    unit_rows = [_extract_unit_row(load_json(path)) for path in unit_reports]
    budget_rows = [_extract_budget_row(load_json(path)) for path in budget_reports]
    audit_rows = read_audit_rows(
        Path(args.llm_audit_log),
        window_days=max(1, int(args.audit_window_days)),
        limit=max(1, int(args.audit_limit)),
    )
    audit_summary = summarize_audit_reasons(audit_rows)
    summary = build_tradeoff_summary(unit_rows, budget_rows, audit_summary)
    failures = evaluate_gate(
        summary,
        min_reports=max(0, int(args.min_reports)),
        min_tradeoff_index=max(0.0, float(args.min_tradeoff_index)),
        max_avg_cost_per_resolved_session=max(0.0, float(args.max_avg_cost_per_resolved_session)),
        max_avg_unresolved_cost_burn_total=max(0.0, float(args.max_avg_unresolved_cost_burn_total)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unit_report_count": len(unit_reports),
        "budget_report_count": len(budget_reports),
        "llm_audit_log": str(args.llm_audit_log),
        "audit_summary": audit_summary,
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_reports": int(args.min_reports),
                "min_tradeoff_index": float(args.min_tradeoff_index),
                "max_avg_cost_per_resolved_session": float(args.max_avg_cost_per_resolved_session),
                "max_avg_unresolved_cost_burn_total": float(args.max_avg_unresolved_cost_burn_total),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"report_count={_safe_int(summary.get('report_count'), 0)}")
    print(f"tradeoff_index={_safe_float(summary.get('tradeoff_index'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
