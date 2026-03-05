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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "committed_at", "generated_at"):
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


def _phase(row: Mapping[str, Any]) -> str:
    text = str(row.get("phase") or row.get("event_type") or row.get("step") or "").strip().upper()
    aliases = {
        "START": "PREPARE",
        "PREPARED": "PREPARE",
        "CHECK": "VALIDATE",
        "VALIDATED": "VALIDATE",
        "EXECUTE": "COMMIT",
        "COMMITTED": "COMMIT",
        "ABORTED": "ABORT",
        "CANCELLED": "ABORT",
    }
    return aliases.get(text, text or "UNKNOWN")


def _tx_key(row: Mapping[str, Any]) -> str:
    tx_id = str(row.get("tx_id") or row.get("transaction_id") or "").strip()
    if tx_id:
        return tx_id
    workflow = str(row.get("workflow_id") or row.get("conversation_id") or "").strip()
    request = str(row.get("request_id") or "").strip()
    return "|".join([workflow, request]).strip("|") or "__missing__"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_tool_tx_fence_model(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    tx_rows: dict[str, list[tuple[datetime, str, Mapping[str, Any]]]] = {}
    inconsistent_state_total = 0
    phase_total = 0

    for row in rows:
        ts = _event_ts(row) or now_dt
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts
        phase = _phase(row)
        tx_rows.setdefault(_tx_key(row), []).append((ts, phase, row))
        phase_total += 1
        if _safe_bool(row.get("inconsistent_state_detected"), False) or _safe_bool(row.get("state_inconsistent"), False):
            inconsistent_state_total += 1

    tx_total = 0
    tx_started_total = 0
    tx_committed_total = 0
    tx_aborted_total = 0
    sequence_violation_total = 0
    optimistic_check_missing_total = 0
    optimistic_mismatch_commit_total = 0
    commit_after_validate_total = 0
    commit_latency_samples: list[float] = []

    for sequence in tx_rows.values():
        ordered = sorted(sequence, key=lambda x: x[0])
        tx_total += 1

        prepare_at: datetime | None = None
        validate_seen = False
        commit_seen = False
        abort_seen = False

        for ts, phase, row in ordered:
            if phase == "PREPARE":
                if prepare_at is None:
                    prepare_at = ts
                tx_started_total += 1 if prepare_at == ts else 0
            elif phase == "VALIDATE":
                validate_seen = True
            elif phase == "COMMIT":
                commit_seen = True
                tx_committed_total += 1
                if prepare_at is None or not validate_seen:
                    sequence_violation_total += 1
                else:
                    commit_after_validate_total += 1
                    commit_latency_samples.append(max(0.0, (ts - prepare_at).total_seconds() * 1000.0))

                check_field_exists = any(
                    key in row for key in ("optimistic_check_passed", "optimistic_check_ok", "optimistic_validate_passed")
                )
                check_passed = _safe_bool(
                    row.get("optimistic_check_passed", row.get("optimistic_check_ok", row.get("optimistic_validate_passed"))),
                    False,
                )
                if not check_field_exists:
                    optimistic_check_missing_total += 1
                elif not check_passed:
                    optimistic_mismatch_commit_total += 1
            elif phase == "ABORT":
                abort_seen = True
                tx_aborted_total += 1

        if not commit_seen and not abort_seen and prepare_at is None:
            sequence_violation_total += 1

    commit_after_validate_ratio = (
        1.0 if tx_committed_total == 0 else float(commit_after_validate_total) / float(tx_committed_total)
    )
    p95_prepare_to_commit_latency_ms = _p95(commit_latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "phase_total": phase_total,
        "tx_total": tx_total,
        "tx_started_total": tx_started_total,
        "tx_committed_total": tx_committed_total,
        "tx_aborted_total": tx_aborted_total,
        "sequence_violation_total": sequence_violation_total,
        "optimistic_check_missing_total": optimistic_check_missing_total,
        "optimistic_mismatch_commit_total": optimistic_mismatch_commit_total,
        "inconsistent_state_total": inconsistent_state_total,
        "commit_after_validate_ratio": commit_after_validate_ratio,
        "p95_prepare_to_commit_latency_ms": p95_prepare_to_commit_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_tx_total: int,
    min_commit_after_validate_ratio: float,
    max_sequence_violation_total: int,
    max_optimistic_check_missing_total: int,
    max_optimistic_mismatch_commit_total: int,
    max_inconsistent_state_total: int,
    max_p95_prepare_to_commit_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    tx_total = _safe_int(summary.get("tx_total"), 0)
    commit_after_validate_ratio = _safe_float(summary.get("commit_after_validate_ratio"), 0.0)
    sequence_violation_total = _safe_int(summary.get("sequence_violation_total"), 0)
    optimistic_check_missing_total = _safe_int(summary.get("optimistic_check_missing_total"), 0)
    optimistic_mismatch_commit_total = _safe_int(summary.get("optimistic_mismatch_commit_total"), 0)
    inconsistent_state_total = _safe_int(summary.get("inconsistent_state_total"), 0)
    p95_prepare_to_commit_latency_ms = _safe_float(summary.get("p95_prepare_to_commit_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat tool tx fence window too small: {window_size} < {int(min_window)}")
    if tx_total < max(0, int(min_tx_total)):
        failures.append(f"chat tool tx total too small: {tx_total} < {int(min_tx_total)}")
    if window_size == 0:
        return failures

    if commit_after_validate_ratio < max(0.0, float(min_commit_after_validate_ratio)):
        failures.append(
            "chat tool tx commit-after-validate ratio below minimum: "
            f"{commit_after_validate_ratio:.4f} < {float(min_commit_after_validate_ratio):.4f}"
        )
    if sequence_violation_total > max(0, int(max_sequence_violation_total)):
        failures.append(
            f"chat tool tx sequence violation total exceeded: {sequence_violation_total} > {int(max_sequence_violation_total)}"
        )
    if optimistic_check_missing_total > max(0, int(max_optimistic_check_missing_total)):
        failures.append(
            "chat tool tx optimistic check missing total exceeded: "
            f"{optimistic_check_missing_total} > {int(max_optimistic_check_missing_total)}"
        )
    if optimistic_mismatch_commit_total > max(0, int(max_optimistic_mismatch_commit_total)):
        failures.append(
            "chat tool tx optimistic mismatch commit total exceeded: "
            f"{optimistic_mismatch_commit_total} > {int(max_optimistic_mismatch_commit_total)}"
        )
    if inconsistent_state_total > max(0, int(max_inconsistent_state_total)):
        failures.append(
            f"chat tool tx inconsistent state total exceeded: {inconsistent_state_total} > {int(max_inconsistent_state_total)}"
        )
    if p95_prepare_to_commit_latency_ms > max(0.0, float(max_p95_prepare_to_commit_latency_ms)):
        failures.append(
            "chat tool tx p95 prepare->commit latency exceeded: "
            f"{p95_prepare_to_commit_latency_ms:.2f}ms > {float(max_p95_prepare_to_commit_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat tool tx fence stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_tx_total_drop: int,
    max_tx_started_total_drop: int,
    max_tx_committed_total_drop: int,
    max_commit_after_validate_ratio_drop: float,
    max_sequence_violation_total_increase: int,
    max_optimistic_check_missing_total_increase: int,
    max_optimistic_mismatch_commit_total_increase: int,
    max_inconsistent_state_total_increase: int,
    max_p95_prepare_to_commit_latency_ms_increase: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("tx_total", max_tx_total_drop),
        ("tx_started_total", max_tx_started_total_drop),
        ("tx_committed_total", max_tx_committed_total_drop),
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

    base_commit_after_validate_ratio = _safe_float(base_summary.get("commit_after_validate_ratio"), 1.0)
    cur_commit_after_validate_ratio = _safe_float(current_summary.get("commit_after_validate_ratio"), 1.0)
    commit_after_validate_ratio_drop = max(0.0, base_commit_after_validate_ratio - cur_commit_after_validate_ratio)
    if commit_after_validate_ratio_drop > max(0.0, float(max_commit_after_validate_ratio_drop)):
        failures.append(
            "commit_after_validate_ratio regression: "
            f"baseline={base_commit_after_validate_ratio:.6f}, current={cur_commit_after_validate_ratio:.6f}, "
            f"allowed_drop={float(max_commit_after_validate_ratio_drop):.6f}"
        )

    baseline_increase_pairs = [
        ("sequence_violation_total", max_sequence_violation_total_increase),
        ("optimistic_check_missing_total", max_optimistic_check_missing_total_increase),
        ("optimistic_mismatch_commit_total", max_optimistic_mismatch_commit_total_increase),
        ("inconsistent_state_total", max_inconsistent_state_total_increase),
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

    base_p95_prepare_to_commit_latency_ms = _safe_float(base_summary.get("p95_prepare_to_commit_latency_ms"), 0.0)
    cur_p95_prepare_to_commit_latency_ms = _safe_float(current_summary.get("p95_prepare_to_commit_latency_ms"), 0.0)
    p95_prepare_to_commit_latency_ms_increase = max(
        0.0, cur_p95_prepare_to_commit_latency_ms - base_p95_prepare_to_commit_latency_ms
    )
    if p95_prepare_to_commit_latency_ms_increase > max(0.0, float(max_p95_prepare_to_commit_latency_ms_increase)):
        failures.append(
            "p95_prepare_to_commit_latency_ms regression: "
            f"baseline={base_p95_prepare_to_commit_latency_ms:.6f}, current={cur_p95_prepare_to_commit_latency_ms:.6f}, "
            f"allowed_increase={float(max_p95_prepare_to_commit_latency_ms_increase):.6f}"
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
    lines.append("# Chat Tool Transaction Fence Model")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- tx_total: {_safe_int(summary.get('tx_total'), 0)}")
    lines.append(f"- tx_committed_total: {_safe_int(summary.get('tx_committed_total'), 0)}")
    lines.append(f"- sequence_violation_total: {_safe_int(summary.get('sequence_violation_total'), 0)}")
    lines.append(f"- optimistic_mismatch_commit_total: {_safe_int(summary.get('optimistic_mismatch_commit_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat tool transaction fence model quality.")
    parser.add_argument("--events-jsonl", default="var/chat_tool_tx/tx_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_tool_tx_fence_model")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-tx-total", type=int, default=0)
    parser.add_argument("--min-commit-after-validate-ratio", type=float, default=0.0)
    parser.add_argument("--max-sequence-violation-total", type=int, default=0)
    parser.add_argument("--max-optimistic-check-missing-total", type=int, default=0)
    parser.add_argument("--max-optimistic-mismatch-commit-total", type=int, default=0)
    parser.add_argument("--max-inconsistent-state-total", type=int, default=0)
    parser.add_argument("--max-p95-prepare-to-commit-latency-ms", type=float, default=1000000.0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-tx-total-drop", type=int, default=10)
    parser.add_argument("--max-tx-started-total-drop", type=int, default=10)
    parser.add_argument("--max-tx-committed-total-drop", type=int, default=10)
    parser.add_argument("--max-commit-after-validate-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-sequence-violation-total-increase", type=int, default=0)
    parser.add_argument("--max-optimistic-check-missing-total-increase", type=int, default=0)
    parser.add_argument("--max-optimistic-mismatch-commit-total-increase", type=int, default=0)
    parser.add_argument("--max-inconsistent-state-total-increase", type=int, default=0)
    parser.add_argument("--max-p95-prepare-to-commit-latency-ms-increase", type=float, default=100.0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_tool_tx_fence_model(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_tx_total=max(0, int(args.min_tx_total)),
        min_commit_after_validate_ratio=max(0.0, float(args.min_commit_after_validate_ratio)),
        max_sequence_violation_total=max(0, int(args.max_sequence_violation_total)),
        max_optimistic_check_missing_total=max(0, int(args.max_optimistic_check_missing_total)),
        max_optimistic_mismatch_commit_total=max(0, int(args.max_optimistic_mismatch_commit_total)),
        max_inconsistent_state_total=max(0, int(args.max_inconsistent_state_total)),
        max_p95_prepare_to_commit_latency_ms=max(0.0, float(args.max_p95_prepare_to_commit_latency_ms)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_tx_total_drop=max(0, int(args.max_tx_total_drop)),
            max_tx_started_total_drop=max(0, int(args.max_tx_started_total_drop)),
            max_tx_committed_total_drop=max(0, int(args.max_tx_committed_total_drop)),
            max_commit_after_validate_ratio_drop=max(0.0, float(args.max_commit_after_validate_ratio_drop)),
            max_sequence_violation_total_increase=max(0, int(args.max_sequence_violation_total_increase)),
            max_optimistic_check_missing_total_increase=max(0, int(args.max_optimistic_check_missing_total_increase)),
            max_optimistic_mismatch_commit_total_increase=max(
                0, int(args.max_optimistic_mismatch_commit_total_increase)
            ),
            max_inconsistent_state_total_increase=max(0, int(args.max_inconsistent_state_total_increase)),
            max_p95_prepare_to_commit_latency_ms_increase=max(
                0.0, float(args.max_p95_prepare_to_commit_latency_ms_increase)
            ),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "source": {
            "events_jsonl": str(args.events_jsonl),
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
                "min_tx_total": int(args.min_tx_total),
                "min_commit_after_validate_ratio": float(args.min_commit_after_validate_ratio),
                "max_sequence_violation_total": int(args.max_sequence_violation_total),
                "max_optimistic_check_missing_total": int(args.max_optimistic_check_missing_total),
                "max_optimistic_mismatch_commit_total": int(args.max_optimistic_mismatch_commit_total),
                "max_inconsistent_state_total": int(args.max_inconsistent_state_total),
                "max_p95_prepare_to_commit_latency_ms": float(args.max_p95_prepare_to_commit_latency_ms),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_tx_total_drop": int(args.max_tx_total_drop),
                "max_tx_started_total_drop": int(args.max_tx_started_total_drop),
                "max_tx_committed_total_drop": int(args.max_tx_committed_total_drop),
                "max_commit_after_validate_ratio_drop": float(args.max_commit_after_validate_ratio_drop),
                "max_sequence_violation_total_increase": int(args.max_sequence_violation_total_increase),
                "max_optimistic_check_missing_total_increase": int(args.max_optimistic_check_missing_total_increase),
                "max_optimistic_mismatch_commit_total_increase": int(args.max_optimistic_mismatch_commit_total_increase),
                "max_inconsistent_state_total_increase": int(args.max_inconsistent_state_total_increase),
                "max_p95_prepare_to_commit_latency_ms_increase": float(args.max_p95_prepare_to_commit_latency_ms_increase),
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
    print(f"tx_total={_safe_int(summary.get('tx_total'), 0)}")
    print(f"sequence_violation_total={_safe_int(summary.get('sequence_violation_total'), 0)}")
    print(f"optimistic_mismatch_commit_total={_safe_int(summary.get('optimistic_mismatch_commit_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
