#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
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


def _safe_ceil(value: float) -> int:
    return int(math.ceil(max(0.0, value)))


def resolve_latest_report(reports_dir: Path, *, prefix: str) -> Path | None:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    if not rows:
        return None
    return rows[-1]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def compute_forecast(
    *,
    load_summary: Mapping[str, Any],
    baseline_window_hours: float,
    weekly_growth_factor: float,
    monthly_growth_factor: float,
    promo_surge_factor: float,
    cpu_rps_per_core: float,
    gpu_tokens_per_sec: float,
    base_memory_gb: float,
    memory_per_core_gb: float,
    cost_per_1k_tokens: float,
) -> dict[str, Any]:
    profiles = load_summary.get("profiles") if isinstance(load_summary.get("profiles"), Mapping) else {}
    normal = profiles.get("NORMAL") if isinstance(profiles.get("NORMAL"), Mapping) else {}
    hourly_profile = load_summary.get("hourly_profile") if isinstance(load_summary.get("hourly_profile"), list) else []

    window_size = max(0, int(load_summary.get("window_size") or 0))
    window_hours = max(1.0, float(baseline_window_hours))

    baseline_requests_per_hour = float(window_size) / window_hours
    baseline_requests_per_week = baseline_requests_per_hour * 24.0 * 7.0

    avg_tokens_per_request = max(0.0, _safe_float(normal.get("avg_tokens"), 0.0))
    tool_calls_per_request = max(0.0, _safe_float(normal.get("tool_calls_per_request"), 0.0))

    week_requests = baseline_requests_per_week * max(0.0, float(weekly_growth_factor))
    month_requests = baseline_requests_per_week * 4.345 * max(0.0, float(monthly_growth_factor))

    week_tokens = week_requests * avg_tokens_per_request
    month_tokens = month_requests * avg_tokens_per_request

    week_tool_calls = week_requests * tool_calls_per_request
    month_tool_calls = month_requests * tool_calls_per_request

    peak_requests_per_hour = baseline_requests_per_hour
    for row in hourly_profile:
        if not isinstance(row, Mapping):
            continue
        peak_requests_per_hour = max(peak_requests_per_hour, _safe_float(row.get("request_total"), 0.0))

    peak_rps = (peak_requests_per_hour * max(0.0, float(promo_surge_factor))) / 3600.0

    cpu_cores_required = _safe_ceil(0.0 if cpu_rps_per_core <= 0 else peak_rps / float(cpu_rps_per_core))

    tokens_per_sec_peak = peak_rps * avg_tokens_per_request
    gpu_required = _safe_ceil(0.0 if gpu_tokens_per_sec <= 0 else tokens_per_sec_peak / float(gpu_tokens_per_sec))

    memory_gb_required = max(0.0, float(base_memory_gb)) + float(cpu_cores_required) * max(0.0, float(memory_per_core_gb))
    monthly_cost_usd = (month_tokens / 1000.0) * max(0.0, float(cost_per_1k_tokens))

    return {
        "baseline": {
            "window_size": window_size,
            "window_hours": window_hours,
            "requests_per_hour": baseline_requests_per_hour,
            "requests_per_week": baseline_requests_per_week,
            "avg_tokens_per_request": avg_tokens_per_request,
            "tool_calls_per_request": tool_calls_per_request,
            "peak_requests_per_hour": peak_requests_per_hour,
        },
        "forecast": {
            "week_requests": week_requests,
            "month_requests": month_requests,
            "week_tokens": week_tokens,
            "month_tokens": month_tokens,
            "week_tool_calls": week_tool_calls,
            "month_tool_calls": month_tool_calls,
            "peak_rps": peak_rps,
            "monthly_cost_usd": monthly_cost_usd,
        },
        "resources": {
            "cpu_cores_required": cpu_cores_required,
            "gpu_required": gpu_required,
            "memory_gb_required": memory_gb_required,
            "tokens_per_sec_peak": tokens_per_sec_peak,
        },
        "assumptions": {
            "weekly_growth_factor": float(weekly_growth_factor),
            "monthly_growth_factor": float(monthly_growth_factor),
            "promo_surge_factor": float(promo_surge_factor),
            "cpu_rps_per_core": float(cpu_rps_per_core),
            "gpu_tokens_per_sec": float(gpu_tokens_per_sec),
            "cost_per_1k_tokens": float(cost_per_1k_tokens),
        },
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_peak_rps: float,
    max_monthly_cost_usd: float,
    max_cpu_cores: int,
    max_gpu_required: int,
) -> list[str]:
    failures: list[str] = []
    baseline = summary.get("baseline") if isinstance(summary.get("baseline"), Mapping) else {}
    forecast = summary.get("forecast") if isinstance(summary.get("forecast"), Mapping) else {}
    resources = summary.get("resources") if isinstance(summary.get("resources"), Mapping) else {}

    window_size = _safe_int(baseline.get("window_size"), 0)
    peak_rps = _safe_float(forecast.get("peak_rps"), 0.0)
    monthly_cost_usd = _safe_float(forecast.get("monthly_cost_usd"), 0.0)
    cpu_cores_required = _safe_int(resources.get("cpu_cores_required"), 0)
    gpu_required = _safe_int(resources.get("gpu_required"), 0)

    if window_size < max(0, int(min_window)):
        failures.append(f"capacity forecast window too small: {window_size} < {int(min_window)}")
    if peak_rps > max(0.0, float(max_peak_rps)):
        failures.append(f"forecast peak_rps exceeded: {peak_rps:.4f} > {float(max_peak_rps):.4f}")
    if monthly_cost_usd > max(0.0, float(max_monthly_cost_usd)):
        failures.append(f"forecast monthly cost exceeded: {monthly_cost_usd:.2f} > {float(max_monthly_cost_usd):.2f}")
    if cpu_cores_required > max(0, int(max_cpu_cores)):
        failures.append(f"forecast cpu cores exceeded: {cpu_cores_required} > {int(max_cpu_cores)}")
    if gpu_required > max(0, int(max_gpu_required)):
        failures.append(f"forecast gpu count exceeded: {gpu_required} > {int(max_gpu_required)}")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_peak_rps_increase: float,
    max_monthly_cost_usd_increase: float,
    max_cpu_cores_increase: int,
    max_gpu_required_increase: int,
) -> list[str]:
    failures: list[str] = []

    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_forecast = base_summary.get("forecast") if isinstance(base_summary.get("forecast"), Mapping) else {}
    cur_forecast = current_summary.get("forecast") if isinstance(current_summary.get("forecast"), Mapping) else {}
    base_resources = base_summary.get("resources") if isinstance(base_summary.get("resources"), Mapping) else {}
    cur_resources = current_summary.get("resources") if isinstance(current_summary.get("resources"), Mapping) else {}

    base_peak_rps = _safe_float(base_forecast.get("peak_rps"), 0.0)
    cur_peak_rps = _safe_float(cur_forecast.get("peak_rps"), 0.0)
    peak_rps_increase = max(0.0, cur_peak_rps - base_peak_rps)
    if peak_rps_increase > max(0.0, float(max_peak_rps_increase)):
        failures.append(
            "peak_rps regression: "
            f"baseline={base_peak_rps:.6f}, current={cur_peak_rps:.6f}, "
            f"allowed_increase={float(max_peak_rps_increase):.6f}"
        )

    base_monthly_cost_usd = _safe_float(base_forecast.get("monthly_cost_usd"), 0.0)
    cur_monthly_cost_usd = _safe_float(cur_forecast.get("monthly_cost_usd"), 0.0)
    monthly_cost_usd_increase = max(0.0, cur_monthly_cost_usd - base_monthly_cost_usd)
    if monthly_cost_usd_increase > max(0.0, float(max_monthly_cost_usd_increase)):
        failures.append(
            "monthly cost regression: "
            f"baseline={base_monthly_cost_usd:.6f}, current={cur_monthly_cost_usd:.6f}, "
            f"allowed_increase={float(max_monthly_cost_usd_increase):.6f}"
        )

    base_cpu_cores = _safe_int(base_resources.get("cpu_cores_required"), 0)
    cur_cpu_cores = _safe_int(cur_resources.get("cpu_cores_required"), 0)
    cpu_cores_increase = max(0, cur_cpu_cores - base_cpu_cores)
    if cpu_cores_increase > max(0, int(max_cpu_cores_increase)):
        failures.append(
            "cpu cores regression: "
            f"baseline={base_cpu_cores}, current={cur_cpu_cores}, "
            f"allowed_increase={max(0, int(max_cpu_cores_increase))}"
        )

    base_gpu_required = _safe_int(base_resources.get("gpu_required"), 0)
    cur_gpu_required = _safe_int(cur_resources.get("gpu_required"), 0)
    gpu_required_increase = max(0, cur_gpu_required - base_gpu_required)
    if gpu_required_increase > max(0, int(max_gpu_required_increase)):
        failures.append(
            "gpu requirement regression: "
            f"baseline={base_gpu_required}, current={cur_gpu_required}, "
            f"allowed_increase={max(0, int(max_gpu_required_increase))}"
        )
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    baseline = summary.get("baseline") if isinstance(summary.get("baseline"), Mapping) else {}
    forecast = summary.get("forecast") if isinstance(summary.get("forecast"), Mapping) else {}
    resources = summary.get("resources") if isinstance(summary.get("resources"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Capacity Forecast")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- load_profile_report: {payload.get('load_profile_report')}")
    lines.append(f"- baseline_window_size: {int(baseline.get('window_size') or 0)}")
    lines.append(f"- week_requests: {_safe_float(forecast.get('week_requests'), 0.0):.1f}")
    lines.append(f"- month_requests: {_safe_float(forecast.get('month_requests'), 0.0):.1f}")
    lines.append(f"- month_tokens: {_safe_float(forecast.get('month_tokens'), 0.0):.1f}")
    lines.append(f"- peak_rps: {_safe_float(forecast.get('peak_rps'), 0.0):.4f}")
    lines.append(f"- monthly_cost_usd: {_safe_float(forecast.get('monthly_cost_usd'), 0.0):.2f}")
    lines.append(f"- cpu_cores_required: {int(resources.get('cpu_cores_required') or 0)}")
    lines.append(f"- gpu_required: {int(resources.get('gpu_required') or 0)}")
    lines.append(f"- memory_gb_required: {_safe_float(resources.get('memory_gb_required'), 0.0):.2f}")

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
    parser = argparse.ArgumentParser(description="Forecast chat demand/resources from latest load profile report.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--load-prefix", default="chat_load_profile_model")
    parser.add_argument("--load-report", default="")
    parser.add_argument("--baseline-window-hours", type=float, default=168.0)
    parser.add_argument("--weekly-growth-factor", type=float, default=1.08)
    parser.add_argument("--monthly-growth-factor", type=float, default=1.35)
    parser.add_argument("--promo-surge-factor", type=float, default=1.60)
    parser.add_argument("--cpu-rps-per-core", type=float, default=3.0)
    parser.add_argument("--gpu-tokens-per-sec", type=float, default=800.0)
    parser.add_argument("--base-memory-gb", type=float, default=2.0)
    parser.add_argument("--memory-per-core-gb", type=float, default=0.5)
    parser.add_argument("--cost-per-1k-tokens", type=float, default=0.002)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_capacity_forecast")
    parser.add_argument("--min-window", type=int, default=1)
    parser.add_argument("--max-peak-rps", type=float, default=50.0)
    parser.add_argument("--max-monthly-cost-usd", type=float, default=15000.0)
    parser.add_argument("--max-cpu-cores", type=int, default=64)
    parser.add_argument("--max-gpu-required", type=int, default=8)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-peak-rps-increase", type=float, default=5.0)
    parser.add_argument("--max-monthly-cost-usd-increase", type=float, default=1000.0)
    parser.add_argument("--max-cpu-cores-increase", type=int, default=4)
    parser.add_argument("--max-gpu-required-increase", type=int, default=1)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report_path: Path | None
    if str(args.load_report).strip():
        report_path = Path(args.load_report)
        if not report_path.exists():
            raise RuntimeError(f"load profile report not found: {report_path}")
    else:
        report_path = resolve_latest_report(Path(args.reports_dir), prefix=str(args.load_prefix))

    if report_path is None:
        load_payload: dict[str, Any] = {}
    else:
        load_payload = load_json(report_path)

    load_summary = load_payload.get("summary") if isinstance(load_payload.get("summary"), Mapping) else {}
    summary = compute_forecast(
        load_summary=load_summary,
        baseline_window_hours=max(1.0, float(args.baseline_window_hours)),
        weekly_growth_factor=max(0.0, float(args.weekly_growth_factor)),
        monthly_growth_factor=max(0.0, float(args.monthly_growth_factor)),
        promo_surge_factor=max(0.0, float(args.promo_surge_factor)),
        cpu_rps_per_core=max(0.0001, float(args.cpu_rps_per_core)),
        gpu_tokens_per_sec=max(0.0001, float(args.gpu_tokens_per_sec)),
        base_memory_gb=max(0.0, float(args.base_memory_gb)),
        memory_per_core_gb=max(0.0, float(args.memory_per_core_gb)),
        cost_per_1k_tokens=max(0.0, float(args.cost_per_1k_tokens)),
    )

    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_peak_rps=max(0.0, float(args.max_peak_rps)),
        max_monthly_cost_usd=max(0.0, float(args.max_monthly_cost_usd)),
        max_cpu_cores=max(0, int(args.max_cpu_cores)),
        max_gpu_required=max(0, int(args.max_gpu_required)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_peak_rps_increase=max(0.0, float(args.max_peak_rps_increase)),
            max_monthly_cost_usd_increase=max(0.0, float(args.max_monthly_cost_usd_increase)),
            max_cpu_cores_increase=max(0, int(args.max_cpu_cores_increase)),
            max_gpu_required_increase=max(0, int(args.max_gpu_required_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "load_profile_report": str(report_path) if report_path else None,
        "source": {
            "reports_dir": str(args.reports_dir),
            "load_prefix": str(args.load_prefix),
            "load_report": str(report_path) if report_path else None,
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
                "max_peak_rps": float(args.max_peak_rps),
                "max_monthly_cost_usd": float(args.max_monthly_cost_usd),
                "max_cpu_cores": int(args.max_cpu_cores),
                "max_gpu_required": int(args.max_gpu_required),
                "max_peak_rps_increase": float(args.max_peak_rps_increase),
                "max_monthly_cost_usd_increase": float(args.max_monthly_cost_usd_increase),
                "max_cpu_cores_increase": int(args.max_cpu_cores_increase),
                "max_gpu_required_increase": int(args.max_gpu_required_increase),
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
    print(f"peak_rps={_safe_float((summary.get('forecast') or {}).get('peak_rps'), 0.0):.4f}")
    print(f"monthly_cost_usd={_safe_float((summary.get('forecast') or {}).get('monthly_cost_usd'), 0.0):.2f}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and not payload["gate"]["pass"]:
        for failure in failures:
            print(f"[gate-failure] {failure}")
        for failure in baseline_failures:
            print(f"[baseline-failure] {failure}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
