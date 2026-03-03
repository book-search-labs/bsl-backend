#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

MODE_ORDER: dict[str, int] = {
    "NORMAL": 0,
    "DEGRADE_LEVEL_1": 1,
    "DEGRADE_LEVEL_2": 2,
    "FAIL_CLOSED": 3,
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def resolve_launch_gate_report(path: str, *, reports_dir: str, prefix: str) -> Path:
    if str(path).strip():
        resolved = Path(path)
        if not resolved.exists():
            raise RuntimeError(f"launch gate report not found: {resolved}")
        return resolved
    base = Path(reports_dir)
    if not base.exists():
        raise RuntimeError(f"reports dir not found: {base}")
    candidates = sorted(base.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        raise RuntimeError(f"no launch gate report found in {base} with prefix={prefix}")
    return candidates[-1]


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


def _safe_mode(value: Any, default: str = "NORMAL") -> str:
    mode = str(value or "").strip().upper()
    if mode in MODE_ORDER:
        return mode
    return default


def read_audit_rows(path: Path, *, window_minutes: int, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
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

    now_dt = now or datetime.now(timezone.utc)
    threshold = now_dt - timedelta(minutes=max(1, int(window_minutes)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _parse_ts(row.get("timestamp"))
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def summarize_audit(rows: list[Mapping[str, Any]], *, window_minutes: int) -> dict[str, Any]:
    total = len(rows)
    ok_total = 0
    error_total = 0
    total_tokens = 0
    total_cost_usd = 0.0
    by_reason: dict[str, int] = {}

    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "ok":
            ok_total += 1
        else:
            error_total += 1
        total_tokens += max(0, _safe_int(row.get("tokens"), 0))
        total_cost_usd += max(0.0, _safe_float(row.get("cost_usd"), 0.0))
        reason_code = str(row.get("reason_code") or "NONE")
        by_reason[reason_code] = by_reason.get(reason_code, 0) + 1

    hours = max(1.0 / 60.0, float(max(1, int(window_minutes))) / 60.0)
    top_reasons = sorted(by_reason.items(), key=lambda item: item[1], reverse=True)
    return {
        "window_size": total,
        "ok_total": ok_total,
        "error_total": error_total,
        "error_ratio": 0.0 if total == 0 else float(error_total) / float(total),
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "tokens_per_hour": float(total_tokens) / hours,
        "cost_usd_per_hour": float(total_cost_usd) / hours,
        "top_reasons": [{"reason_code": code, "count": count} for code, count in top_reasons[:10]],
    }


def decide_guard_mode(
    *,
    audit_summary: Mapping[str, Any],
    perf_summary: Mapping[str, Any],
    completion_summary: Mapping[str, Any],
    max_audit_error_ratio: float,
    max_cost_usd_per_hour: float,
    max_tokens_per_hour: float,
    max_llm_p95_ms: float,
    max_fallback_ratio: float,
    max_insufficient_evidence_ratio: float,
) -> dict[str, Any]:
    breaches: list[str] = []
    severe_breaches: list[str] = []

    error_ratio = float(audit_summary.get("error_ratio") or 0.0)
    cost_usd_per_hour = float(audit_summary.get("cost_usd_per_hour") or 0.0)
    tokens_per_hour = float(audit_summary.get("tokens_per_hour") or 0.0)
    llm_p95_ms = float(perf_summary.get("llm_p95_ms") or 0.0)
    fallback_ratio = float(perf_summary.get("fallback_ratio") or 0.0)
    insufficient_ratio = float(completion_summary.get("insufficient_evidence_ratio") or 0.0)
    llm_count = int(perf_summary.get("llm_count") or 0)

    def _register(name: str, value: float, threshold: float) -> None:
        if value <= threshold:
            return
        breaches.append(f"{name} exceeded: {value:.4f} > {threshold:.4f}")
        if threshold > 0.0 and value > threshold * 1.5:
            severe_breaches.append(name)

    _register("audit_error_ratio", error_ratio, max_audit_error_ratio)
    _register("cost_usd_per_hour", cost_usd_per_hour, max_cost_usd_per_hour)
    _register("tokens_per_hour", tokens_per_hour, max_tokens_per_hour)
    if llm_count > 0:
        _register("llm_p95_ms", llm_p95_ms, max_llm_p95_ms)
    _register("fallback_ratio", fallback_ratio, max_fallback_ratio)
    _register("insufficient_evidence_ratio", insufficient_ratio, max_insufficient_evidence_ratio)

    mode = "NORMAL"
    if severe_breaches and len(severe_breaches) >= 2:
        mode = "FAIL_CLOSED"
    elif severe_breaches or len(breaches) >= 3:
        mode = "DEGRADE_LEVEL_2"
    elif breaches:
        mode = "DEGRADE_LEVEL_1"

    actions_by_mode: dict[str, list[str]] = {
        "NORMAL": [
            "현재 설정을 유지하고 비용/오류율 추이를 모니터링합니다.",
        ],
        "DEGRADE_LEVEL_1": [
            "비핵심 intent의 max context/docs를 축소하고 캐시 우선 응답을 강제합니다.",
            "tool parallelism 및 timeout budget을 1차 축소해 fallback 급증을 억제합니다.",
        ],
        "DEGRADE_LEVEL_2": [
            "비핵심 intent에 admission을 적용하고 heavy LLM path를 제한합니다.",
            "추천/탐색 계열은 요약형 fallback으로 단계 강등하고 커머스 intent를 우선 보존합니다.",
        ],
        "FAIL_CLOSED": [
            "chat.engine을 legacy-safe 모드로 강제하고 온콜 에스컬레이션을 즉시 발행합니다.",
            "롤백 완료 전까지 신규 canary 승격을 차단합니다.",
        ],
    }

    return {
        "mode": mode,
        "breaches": breaches,
        "severe_breaches": severe_breaches,
        "recommended_actions": actions_by_mode.get(mode, []),
        "priority_preserve_intents": [
            "ORDER_STATUS",
            "DELIVERY_TRACKING",
            "CANCEL_ORDER",
            "REFUND_REQUEST",
        ],
    }


def evaluate_gate(decision: Mapping[str, Any], *, max_mode: str) -> list[str]:
    failures: list[str] = []
    selected = _safe_mode(decision.get("mode"), "NORMAL")
    allowed = _safe_mode(max_mode, "DEGRADE_LEVEL_1")
    selected_order = MODE_ORDER.get(selected)
    allowed_order = MODE_ORDER.get(allowed)

    if selected_order is None:
        failures.append(f"unknown decision mode: {selected}")
        return failures
    if allowed_order is None:
        failures.append(f"unknown max_mode: {allowed}")
        return failures
    if selected_order > allowed_order:
        failures.append(f"capacity guard mode exceeded: {selected} > allowed {allowed}")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    *,
    current_decision: Mapping[str, Any],
    current_audit_summary: Mapping[str, Any],
    current_perf_summary: Mapping[str, Any],
    max_mode_step_increase: int,
    max_error_ratio_increase: float,
    max_cost_usd_per_hour_increase: float,
    max_fallback_ratio_increase: float,
    max_llm_p95_ms_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_decision = baseline_report.get("decision") if isinstance(baseline_report.get("decision"), Mapping) else {}
    base_audit = (
        baseline_report.get("audit_summary") if isinstance(baseline_report.get("audit_summary"), Mapping) else {}
    )
    base_perf = baseline_report.get("perf_summary") if isinstance(baseline_report.get("perf_summary"), Mapping) else {}

    if isinstance(base_derived, Mapping):
        if not base_decision and isinstance(base_derived.get("decision"), Mapping):
            base_decision = base_derived.get("decision")  # type: ignore[assignment]
        if not base_audit and isinstance(base_derived.get("audit_summary"), Mapping):
            base_audit = base_derived.get("audit_summary")  # type: ignore[assignment]
        if not base_perf and isinstance(base_derived.get("perf_summary"), Mapping):
            base_perf = base_derived.get("perf_summary")  # type: ignore[assignment]

    base_mode = _safe_mode(base_decision.get("mode"), "NORMAL")
    cur_mode = _safe_mode(current_decision.get("mode"), "NORMAL")
    mode_step = max(0, MODE_ORDER[cur_mode] - MODE_ORDER[base_mode])
    if mode_step > max(0, int(max_mode_step_increase)):
        failures.append(
            "guard mode regression: "
            f"baseline={base_mode}, current={cur_mode}, allowed_step={max(0, int(max_mode_step_increase))}"
        )

    base_error_ratio = float(base_audit.get("error_ratio") or 0.0)
    cur_error_ratio = float(current_audit_summary.get("error_ratio") or 0.0)
    error_ratio_increase = max(0.0, cur_error_ratio - base_error_ratio)
    if error_ratio_increase > max(0.0, float(max_error_ratio_increase)):
        failures.append(
            "audit error ratio regression: "
            f"baseline={base_error_ratio:.6f}, current={cur_error_ratio:.6f}, "
            f"allowed_increase={float(max_error_ratio_increase):.6f}"
        )

    base_cost_per_hour = float(base_audit.get("cost_usd_per_hour") or 0.0)
    cur_cost_per_hour = float(current_audit_summary.get("cost_usd_per_hour") or 0.0)
    cost_increase = max(0.0, cur_cost_per_hour - base_cost_per_hour)
    if cost_increase > max(0.0, float(max_cost_usd_per_hour_increase)):
        failures.append(
            "cost per hour regression: "
            f"baseline={base_cost_per_hour:.6f}, current={cur_cost_per_hour:.6f}, "
            f"allowed_increase={float(max_cost_usd_per_hour_increase):.6f}"
        )

    base_fallback = float(base_perf.get("fallback_ratio") or 0.0)
    cur_fallback = float(current_perf_summary.get("fallback_ratio") or 0.0)
    fallback_increase = max(0.0, cur_fallback - base_fallback)
    if fallback_increase > max(0.0, float(max_fallback_ratio_increase)):
        failures.append(
            "fallback ratio regression: "
            f"baseline={base_fallback:.6f}, current={cur_fallback:.6f}, "
            f"allowed_increase={float(max_fallback_ratio_increase):.6f}"
        )

    base_llm_p95 = float(base_perf.get("llm_p95_ms") or 0.0)
    cur_llm_p95 = float(current_perf_summary.get("llm_p95_ms") or 0.0)
    llm_p95_increase = max(0.0, cur_llm_p95 - base_llm_p95)
    if llm_p95_increase > max(0.0, float(max_llm_p95_ms_increase)):
        failures.append(
            "llm p95 regression: "
            f"baseline={base_llm_p95:.6f}, current={cur_llm_p95:.6f}, "
            f"allowed_increase={float(max_llm_p95_ms_increase):.6f}"
        )

    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    decision = report.get("decision") if isinstance(report.get("decision"), Mapping) else {}
    audit_summary = report.get("audit_summary") if isinstance(report.get("audit_summary"), Mapping) else {}
    perf_summary = report.get("perf_summary") if isinstance(report.get("perf_summary"), Mapping) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Capacity/Cost Guard Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- report_path: {report.get('report_path')}")
    lines.append(f"- audit_log_path: {report.get('audit_log_path')}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- mode: {decision.get('mode')}")
    lines.append(f"- breaches: {len(decision.get('breaches') or [])}")
    lines.append("")
    lines.append("## Signals")
    lines.append("")
    lines.append(f"- audit_error_ratio: {float(audit_summary.get('error_ratio') or 0.0):.6f}")
    lines.append(f"- cost_usd_per_hour: {float(audit_summary.get('cost_usd_per_hour') or 0.0):.6f}")
    lines.append(f"- tokens_per_hour: {float(audit_summary.get('tokens_per_hour') or 0.0):.6f}")
    lines.append(f"- llm_p95_ms: {float(perf_summary.get('llm_p95_ms') or 0.0):.6f}")
    lines.append(f"- fallback_ratio: {float(perf_summary.get('fallback_ratio') or 0.0):.6f}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    if failures:
        lines.append("- failures:")
        for item in failures:
            lines.append(f"  - {item}")
    if baseline_failures:
        lines.append("- baseline_failures:")
        for item in baseline_failures:
            lines.append(f"  - {item}")
    if not failures and not baseline_failures:
        lines.append("- failures: none")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat capacity/cost guard mode from launch report + llm audit logs.")
    parser.add_argument("--launch-gate-report", default="")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--report-prefix", default="chat_production_launch_gate")
    parser.add_argument("--llm-audit-log", default="var/llm_gateway/audit.log")
    parser.add_argument("--audit-window-minutes", type=int, default=60)
    parser.add_argument("--audit-limit", type=int, default=5000)
    parser.add_argument("--max-audit-error-ratio", type=float, default=0.08)
    parser.add_argument("--max-cost-usd-per-hour", type=float, default=5.0)
    parser.add_argument("--max-tokens-per-hour", type=float, default=300000.0)
    parser.add_argument("--max-llm-p95-ms", type=float, default=4000.0)
    parser.add_argument("--max-fallback-ratio", type=float, default=0.15)
    parser.add_argument("--max-insufficient-evidence-ratio", type=float, default=0.30)
    parser.add_argument("--max-mode", choices=list(MODE_ORDER.keys()), default="DEGRADE_LEVEL_1")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--output-prefix", default="chat_capacity_cost_guard")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-mode-step-increase", type=int, default=0)
    parser.add_argument("--max-audit-error-ratio-increase", type=float, default=0.02)
    parser.add_argument("--max-cost-usd-per-hour-increase", type=float, default=2.0)
    parser.add_argument("--max-fallback-ratio-increase", type=float, default=0.05)
    parser.add_argument("--max-llm-p95-ms-increase", type=float, default=800.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report_path = resolve_launch_gate_report(
        args.launch_gate_report,
        reports_dir=args.reports_dir,
        prefix=args.report_prefix,
    )
    report = load_json(report_path)
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    perf_summary = derived.get("perf") if isinstance(derived.get("perf"), Mapping) else {}
    completion_summary = derived.get("completion") if isinstance(derived.get("completion"), Mapping) else {}

    audit_path = Path(args.llm_audit_log)
    audit_rows = read_audit_rows(
        audit_path,
        window_minutes=max(1, int(args.audit_window_minutes)),
        limit=max(1, int(args.audit_limit)),
    )
    audit_summary = summarize_audit(audit_rows, window_minutes=max(1, int(args.audit_window_minutes)))
    decision = decide_guard_mode(
        audit_summary=audit_summary,
        perf_summary=perf_summary,
        completion_summary=completion_summary,
        max_audit_error_ratio=max(0.0, float(args.max_audit_error_ratio)),
        max_cost_usd_per_hour=max(0.0, float(args.max_cost_usd_per_hour)),
        max_tokens_per_hour=max(0.0, float(args.max_tokens_per_hour)),
        max_llm_p95_ms=max(0.0, float(args.max_llm_p95_ms)),
        max_fallback_ratio=max(0.0, float(args.max_fallback_ratio)),
        max_insufficient_evidence_ratio=max(0.0, float(args.max_insufficient_evidence_ratio)),
    )
    failures = evaluate_gate(decision, max_mode=str(args.max_mode))
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            current_decision=decision,
            current_audit_summary=audit_summary,
            current_perf_summary=perf_summary,
            max_mode_step_increase=max(0, int(args.max_mode_step_increase)),
            max_error_ratio_increase=max(0.0, float(args.max_audit_error_ratio_increase)),
            max_cost_usd_per_hour_increase=max(0.0, float(args.max_cost_usd_per_hour_increase)),
            max_fallback_ratio_increase=max(0.0, float(args.max_fallback_ratio_increase)),
            max_llm_p95_ms_increase=max(0.0, float(args.max_llm_p95_ms_increase)),
        )

    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "reports_dir": str(args.reports_dir),
            "report_prefix": str(args.report_prefix),
            "launch_gate_report": str(args.launch_gate_report) if args.launch_gate_report else None,
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
            "llm_audit_log": str(args.llm_audit_log),
            "audit_window_minutes": max(1, int(args.audit_window_minutes)),
            "audit_limit": max(1, int(args.audit_limit)),
        },
        "report_path": str(report_path),
        "audit_log_path": str(audit_path),
        "audit_summary": audit_summary,
        "perf_summary": {
            "window_size": int(perf_summary.get("window_size") or 0),
            "llm_count": int(perf_summary.get("llm_count") or 0),
            "llm_p95_ms": float(perf_summary.get("llm_p95_ms") or 0.0),
            "fallback_ratio": float(perf_summary.get("fallback_ratio") or 0.0),
        },
        "completion_summary": {
            "run_total": int(completion_summary.get("run_total") or 0),
            "insufficient_evidence_ratio": float(completion_summary.get("insufficient_evidence_ratio") or 0.0),
            "commerce_completion_rate": float(completion_summary.get("commerce_completion_rate") or 0.0),
        },
        "decision": decision,
        "derived": {
            "audit_summary": audit_summary,
            "perf_summary": {
                "window_size": int(perf_summary.get("window_size") or 0),
                "llm_count": int(perf_summary.get("llm_count") or 0),
                "llm_p95_ms": float(perf_summary.get("llm_p95_ms") or 0.0),
                "fallback_ratio": float(perf_summary.get("fallback_ratio") or 0.0),
            },
            "completion_summary": {
                "run_total": int(completion_summary.get("run_total") or 0),
                "insufficient_evidence_ratio": float(completion_summary.get("insufficient_evidence_ratio") or 0.0),
                "commerce_completion_rate": float(completion_summary.get("commerce_completion_rate") or 0.0),
            },
            "decision": decision,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "max_mode": str(args.max_mode),
                "max_audit_error_ratio": float(args.max_audit_error_ratio),
                "max_cost_usd_per_hour": float(args.max_cost_usd_per_hour),
                "max_tokens_per_hour": float(args.max_tokens_per_hour),
                "max_llm_p95_ms": float(args.max_llm_p95_ms),
                "max_fallback_ratio": float(args.max_fallback_ratio),
                "max_insufficient_evidence_ratio": float(args.max_insufficient_evidence_ratio),
                "max_mode_step_increase": int(args.max_mode_step_increase),
                "max_audit_error_ratio_increase": float(args.max_audit_error_ratio_increase),
                "max_cost_usd_per_hour_increase": float(args.max_cost_usd_per_hour_increase),
                "max_fallback_ratio_increase": float(args.max_fallback_ratio_increase),
                "max_llm_p95_ms_increase": float(args.max_llm_p95_ms_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.output_prefix}_{stamp}.json"
    md_path = out_dir / f"{args.output_prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report_payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"gate_pass={str(report_payload['gate']['pass']).lower()}")
    if args.gate and not report_payload["gate"]["pass"]:
        for item in failures:
            print(f"[gate-failure] {item}")
        for item in baseline_failures:
            print(f"[baseline-failure] {item}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
