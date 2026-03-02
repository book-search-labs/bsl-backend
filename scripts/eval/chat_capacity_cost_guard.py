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
    selected = str(decision.get("mode") or "NORMAL").strip().upper()
    allowed = str(max_mode or "DEGRADE_LEVEL_1").strip().upper()
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

    payload = {
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
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "max_mode": str(args.max_mode),
                "max_audit_error_ratio": float(args.max_audit_error_ratio),
                "max_cost_usd_per_hour": float(args.max_cost_usd_per_hour),
                "max_tokens_per_hour": float(args.max_tokens_per_hour),
                "max_llm_p95_ms": float(args.max_llm_p95_ms),
                "max_fallback_ratio": float(args.max_fallback_ratio),
                "max_insufficient_evidence_ratio": float(args.max_insufficient_evidence_ratio),
            },
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
