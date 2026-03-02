#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def resolve_reports(reports_dir: Path, *, prefix: str, limit: int) -> list[Path]:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    return rows[-max(1, int(limit)) :]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


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


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def build_trend_summary(paths: list[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = load_json(path)
        generated_at = _parse_ts(payload.get("generated_at"))
        if generated_at is None:
            continue
        readiness = payload.get("readiness") if isinstance(payload.get("readiness"), Mapping) else {}
        rows.append(
            {
                "path": str(path),
                "generated_at": generated_at,
                "score": _safe_float(readiness.get("total_score"), 0.0),
                "tier": str(readiness.get("tier") or ""),
                "action": str(readiness.get("recommended_action") or ""),
            }
        )

    rows.sort(key=lambda item: item["generated_at"])
    week_buckets: dict[str, list[float]] = {}
    month_buckets: dict[str, list[float]] = {}
    for row in rows:
        ts = row["generated_at"]
        iso = ts.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        month_key = f"{ts.year}-{ts.month:02d}"
        week_buckets.setdefault(week_key, []).append(float(row["score"]))
        month_buckets.setdefault(month_key, []).append(float(row["score"]))

    week_keys = sorted(week_buckets.keys())
    month_keys = sorted(month_buckets.keys())
    current_week = week_keys[-1] if week_keys else ""
    previous_week = week_keys[-2] if len(week_keys) >= 2 else ""
    current_month = month_keys[-1] if month_keys else ""
    previous_month = month_keys[-2] if len(month_keys) >= 2 else ""

    current_week_avg = _avg(week_buckets.get(current_week, []))
    previous_week_avg = _avg(week_buckets.get(previous_week, []))
    current_month_avg = _avg(month_buckets.get(current_month, []))
    previous_month_avg = _avg(month_buckets.get(previous_month, []))

    weekly_delta = current_week_avg - previous_week_avg if previous_week else 0.0
    monthly_delta = current_month_avg - previous_month_avg if previous_month else 0.0

    target_next_week = max(0.0, min(100.0, current_week_avg + (2.0 if weekly_delta < 0 else 1.0)))
    target_next_month = max(0.0, min(100.0, current_month_avg + (2.0 if monthly_delta < 0 else 1.0)))

    samples = [
        {
            "path": row["path"],
            "generated_at": row["generated_at"].isoformat(),
            "score": row["score"],
            "tier": row["tier"],
            "action": row["action"],
        }
        for row in rows[-20:]
    ]

    return {
        "report_total": len(rows),
        "week_buckets": {key: _avg(value) for key, value in week_buckets.items()},
        "month_buckets": {key: _avg(value) for key, value in month_buckets.items()},
        "current_week": current_week,
        "previous_week": previous_week,
        "current_week_avg": current_week_avg,
        "previous_week_avg": previous_week_avg,
        "weekly_delta": weekly_delta,
        "current_month": current_month,
        "previous_month": previous_month,
        "current_month_avg": current_month_avg,
        "previous_month_avg": previous_month_avg,
        "monthly_delta": monthly_delta,
        "target_next_week": target_next_week,
        "target_next_month": target_next_month,
        "samples": samples,
    }


def evaluate_gate(summary: Mapping[str, Any], *, min_reports: int, min_week_avg: float, min_month_avg: float) -> list[str]:
    failures: list[str] = []
    report_total = int(summary.get("report_total") or 0)
    week_avg = _safe_float(summary.get("current_week_avg"), 0.0)
    month_avg = _safe_float(summary.get("current_month_avg"), 0.0)

    if report_total < max(0, int(min_reports)):
        failures.append(f"insufficient readiness reports: {report_total} < {int(min_reports)}")
    if week_avg < max(0.0, float(min_week_avg)):
        failures.append(f"current week average below threshold: {week_avg:.2f} < {float(min_week_avg):.2f}")
    if month_avg < max(0.0, float(min_month_avg)):
        failures.append(f"current month average below threshold: {month_avg:.2f} < {float(min_month_avg):.2f}")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Readiness Trend")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- report_total: {summary.get('report_total')}")
    lines.append(f"- current_week_avg: {float(summary.get('current_week_avg') or 0.0):.2f}")
    lines.append(f"- previous_week_avg: {float(summary.get('previous_week_avg') or 0.0):.2f}")
    lines.append(f"- weekly_delta: {float(summary.get('weekly_delta') or 0.0):+.2f}")
    lines.append(f"- target_next_week: {float(summary.get('target_next_week') or 0.0):.2f}")
    lines.append(f"- current_month_avg: {float(summary.get('current_month_avg') or 0.0):.2f}")
    lines.append(f"- previous_month_avg: {float(summary.get('previous_month_avg') or 0.0):.2f}")
    lines.append(f"- monthly_delta: {float(summary.get('monthly_delta') or 0.0):+.2f}")
    lines.append(f"- target_next_month: {float(summary.get('target_next_month') or 0.0):.2f}")
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
    parser = argparse.ArgumentParser(description="Summarize chat readiness score trend and derive weekly/monthly targets.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_readiness_score")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--report-prefix", default="chat_readiness_trend")
    parser.add_argument("--min-reports", type=int, default=1)
    parser.add_argument("--min-week-avg", type=float, default=80.0)
    parser.add_argument("--min-month-avg", type=float, default=80.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    paths = resolve_reports(Path(args.reports_dir), prefix=str(args.prefix), limit=max(1, int(args.limit)))
    summary = build_trend_summary(paths)
    failures = evaluate_gate(
        summary,
        min_reports=max(0, int(args.min_reports)),
        min_week_avg=max(0.0, float(args.min_week_avg)),
        min_month_avg=max(0.0, float(args.min_month_avg)),
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_reports": int(args.min_reports),
                "min_week_avg": float(args.min_week_avg),
                "min_month_avg": float(args.min_month_avg),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.report_prefix}_{stamp}.json"
    md_path = out_dir / f"{args.report_prefix}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"current_week_avg={_safe_float(summary.get('current_week_avg'), 0.0):.2f}")
    print(f"current_month_avg={_safe_float(summary.get('current_month_avg'), 0.0):.2f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
