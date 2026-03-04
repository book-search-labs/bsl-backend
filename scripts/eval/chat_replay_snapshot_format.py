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


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {str(k): v for k, v in payload.items()}


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


def _snapshot_ts(row: Mapping[str, Any], path: Path | None = None) -> datetime | None:
    for key in ("recorded_at", "created_at", "timestamp", "event_time", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    if path is not None and path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return None


def _iter_snapshot_files(replay_dir: Path) -> list[Path]:
    runs_dir = replay_dir / "runs"
    candidates: list[Path] = []
    if runs_dir.exists():
        candidates.extend(sorted(runs_dir.rglob("*.json")))
    else:
        candidates.extend(sorted(replay_dir.rglob("*.json")))
    return candidates


def read_snapshots(replay_dir: Path, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
    if not replay_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in _iter_snapshot_files(replay_dir):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, Mapping):
            row = {str(k): v for k, v in payload.items()}
            row["_snapshot_path"] = str(path)
            rows.append(row)
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    threshold = datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours)))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        path = Path(str(row.get("_snapshot_path") or ""))
        ts = _snapshot_ts(row, path if path.exists() else None)
        if ts is not None and ts < threshold:
            continue
        filtered.append(row)
    return filtered


def _has_tool_io(row: Mapping[str, Any]) -> bool:
    for key in ("tool_calls", "tool_io", "tool_events", "executed_tools"):
        value = row.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
        if isinstance(value, Mapping) and len(value) > 0:
            return True
    return False


def summarize_snapshot_format(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    snapshot_total = 0
    missing_request_payload_total = 0
    missing_policy_version_total = 0
    missing_prompt_template_total = 0
    missing_tool_io_total = 0
    missing_budget_state_total = 0
    missing_seed_total = 0

    for row in rows:
        snapshot_total += 1
        path = Path(str(row.get("_snapshot_path") or ""))
        ts = _snapshot_ts(row, path if path.exists() else None)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not isinstance(row.get("request_payload"), Mapping):
            missing_request_payload_total += 1

        policy_version = str(row.get("policy_version") or row.get("policy_bundle_version") or "").strip()
        if not policy_version:
            missing_policy_version_total += 1

        prompt_template = str(row.get("prompt_template") or row.get("prompt_version") or row.get("prompt_id") or "").strip()
        if not prompt_template:
            missing_prompt_template_total += 1

        if not _has_tool_io(row):
            missing_tool_io_total += 1

        budget_state = row.get("budget_state") or row.get("reasoning_budget") or row.get("budget")
        has_budget_state = isinstance(budget_state, Mapping) and len(budget_state) > 0
        if not has_budget_state:
            missing_budget_state_total += 1

        seed = str(row.get("seed") or row.get("replay_seed") or "").strip()
        if not seed:
            missing_seed_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "snapshot_total": snapshot_total,
        "missing_request_payload_total": missing_request_payload_total,
        "missing_policy_version_total": missing_policy_version_total,
        "missing_prompt_template_total": missing_prompt_template_total,
        "missing_tool_io_total": missing_tool_io_total,
        "missing_budget_state_total": missing_budget_state_total,
        "missing_seed_total": missing_seed_total,
        "latest_snapshot_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_request_payload_total: int,
    max_missing_policy_version_total: int,
    max_missing_prompt_template_total: int,
    max_missing_tool_io_total: int,
    max_missing_budget_state_total: int,
    max_missing_seed_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_request_payload_total = _safe_int(summary.get("missing_request_payload_total"), 0)
    missing_policy_version_total = _safe_int(summary.get("missing_policy_version_total"), 0)
    missing_prompt_template_total = _safe_int(summary.get("missing_prompt_template_total"), 0)
    missing_tool_io_total = _safe_int(summary.get("missing_tool_io_total"), 0)
    missing_budget_state_total = _safe_int(summary.get("missing_budget_state_total"), 0)
    missing_seed_total = _safe_int(summary.get("missing_seed_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"replay snapshot window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_request_payload_total > max(0, int(max_missing_request_payload_total)):
        failures.append(
            "replay snapshot missing request payload total exceeded: "
            f"{missing_request_payload_total} > {int(max_missing_request_payload_total)}"
        )
    if missing_policy_version_total > max(0, int(max_missing_policy_version_total)):
        failures.append(
            "replay snapshot missing policy version total exceeded: "
            f"{missing_policy_version_total} > {int(max_missing_policy_version_total)}"
        )
    if missing_prompt_template_total > max(0, int(max_missing_prompt_template_total)):
        failures.append(
            "replay snapshot missing prompt template total exceeded: "
            f"{missing_prompt_template_total} > {int(max_missing_prompt_template_total)}"
        )
    if missing_tool_io_total > max(0, int(max_missing_tool_io_total)):
        failures.append(f"replay snapshot missing tool io total exceeded: {missing_tool_io_total} > {int(max_missing_tool_io_total)}")
    if missing_budget_state_total > max(0, int(max_missing_budget_state_total)):
        failures.append(
            f"replay snapshot missing budget state total exceeded: {missing_budget_state_total} > {int(max_missing_budget_state_total)}"
        )
    if missing_seed_total > max(0, int(max_missing_seed_total)):
        failures.append(f"replay snapshot missing seed total exceeded: {missing_seed_total} > {int(max_missing_seed_total)}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"replay snapshot stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_snapshot_total_drop: int,
    max_missing_request_payload_total_increase: int,
    max_missing_policy_version_total_increase: int,
    max_missing_prompt_template_total_increase: int,
    max_missing_tool_io_total_increase: int,
    max_missing_budget_state_total_increase: int,
    max_missing_seed_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_snapshot_total = _safe_int(base_summary.get("snapshot_total"), 0)
    cur_snapshot_total = _safe_int(current_summary.get("snapshot_total"), 0)
    snapshot_total_drop = max(0, base_snapshot_total - cur_snapshot_total)
    if snapshot_total_drop > max(0, int(max_snapshot_total_drop)):
        failures.append(
            "snapshot_total regression: "
            f"baseline={base_snapshot_total}, current={cur_snapshot_total}, "
            f"allowed_drop={max(0, int(max_snapshot_total_drop))}"
        )

    baseline_increase_pairs = [
        ("missing_request_payload_total", max_missing_request_payload_total_increase),
        ("missing_policy_version_total", max_missing_policy_version_total_increase),
        ("missing_prompt_template_total", max_missing_prompt_template_total_increase),
        ("missing_tool_io_total", max_missing_tool_io_total_increase),
        ("missing_budget_state_total", max_missing_budget_state_total_increase),
        ("missing_seed_total", max_missing_seed_total_increase),
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
    lines.append("# Chat Replay Snapshot Format")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- replay_dir: {payload.get('replay_dir')}")
    lines.append(f"- snapshot_total: {_safe_int(summary.get('snapshot_total'), 0)}")
    lines.append(f"- missing_request_payload_total: {_safe_int(summary.get('missing_request_payload_total'), 0)}")
    lines.append(f"- missing_tool_io_total: {_safe_int(summary.get('missing_tool_io_total'), 0)}")
    lines.append(f"- missing_seed_total: {_safe_int(summary.get('missing_seed_total'), 0)}")
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
    if not failures and not baseline_failures:
        lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate replay snapshot format completeness.")
    parser.add_argument("--replay-dir", default="var/chat_graph/replay")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_replay_snapshot_format")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-missing-request-payload-total", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total", type=int, default=0)
    parser.add_argument("--max-missing-prompt-template-total", type=int, default=0)
    parser.add_argument("--max-missing-tool-io-total", type=int, default=0)
    parser.add_argument("--max-missing-budget-state-total", type=int, default=0)
    parser.add_argument("--max-missing-seed-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-snapshot-total-drop", type=int, default=10)
    parser.add_argument("--max-missing-request-payload-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-prompt-template-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-tool-io-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-budget-state-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-seed-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    replay_dir = Path(args.replay_dir)
    rows = read_snapshots(
        replay_dir,
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_snapshot_format(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_request_payload_total=max(0, int(args.max_missing_request_payload_total)),
        max_missing_policy_version_total=max(0, int(args.max_missing_policy_version_total)),
        max_missing_prompt_template_total=max(0, int(args.max_missing_prompt_template_total)),
        max_missing_tool_io_total=max(0, int(args.max_missing_tool_io_total)),
        max_missing_budget_state_total=max(0, int(args.max_missing_budget_state_total)),
        max_missing_seed_total=max(0, int(args.max_missing_seed_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_snapshot_total_drop=max(0, int(args.max_snapshot_total_drop)),
            max_missing_request_payload_total_increase=max(0, int(args.max_missing_request_payload_total_increase)),
            max_missing_policy_version_total_increase=max(0, int(args.max_missing_policy_version_total_increase)),
            max_missing_prompt_template_total_increase=max(0, int(args.max_missing_prompt_template_total_increase)),
            max_missing_tool_io_total_increase=max(0, int(args.max_missing_tool_io_total_increase)),
            max_missing_budget_state_total_increase=max(0, int(args.max_missing_budget_state_total_increase)),
            max_missing_seed_total_increase=max(0, int(args.max_missing_seed_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "replay_dir": str(replay_dir),
        "source": {
            "replay_dir": str(replay_dir),
            "window_hours": int(args.window_hours),
            "limit": int(args.limit),
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
                "max_missing_request_payload_total": int(args.max_missing_request_payload_total),
                "max_missing_policy_version_total": int(args.max_missing_policy_version_total),
                "max_missing_prompt_template_total": int(args.max_missing_prompt_template_total),
                "max_missing_tool_io_total": int(args.max_missing_tool_io_total),
                "max_missing_budget_state_total": int(args.max_missing_budget_state_total),
                "max_missing_seed_total": int(args.max_missing_seed_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_snapshot_total_drop": int(args.max_snapshot_total_drop),
                "max_missing_request_payload_total_increase": int(args.max_missing_request_payload_total_increase),
                "max_missing_policy_version_total_increase": int(args.max_missing_policy_version_total_increase),
                "max_missing_prompt_template_total_increase": int(args.max_missing_prompt_template_total_increase),
                "max_missing_tool_io_total_increase": int(args.max_missing_tool_io_total_increase),
                "max_missing_budget_state_total_increase": int(args.max_missing_budget_state_total_increase),
                "max_missing_seed_total_increase": int(args.max_missing_seed_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
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
    print(f"snapshot_total={_safe_int(summary.get('snapshot_total'), 0)}")
    print(f"missing_request_payload_total={_safe_int(summary.get('missing_request_payload_total'), 0)}")
    print(f"missing_seed_total={_safe_int(summary.get('missing_seed_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
