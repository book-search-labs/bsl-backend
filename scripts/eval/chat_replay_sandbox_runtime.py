#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_MODES = {"MOCK", "REAL"}
VALID_RESULTS = {"PASS", "FAIL", "ERROR", "TIMEOUT"}


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


def _normalize_mode(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"STUB": "MOCK", "SIMULATED": "MOCK", "LIVE": "REAL"}
    if text in VALID_MODES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def _normalize_result(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"OK": "PASS", "SUCCESS": "PASS"}
    if text in VALID_RESULTS:
        return text
    return aliases.get(text, text or "UNKNOWN")


def summarize_sandbox_runtime(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    run_total = 0
    mock_total = 0
    real_total = 0
    missing_mode_total = 0
    invalid_result_total = 0
    missing_seed_total = 0
    missing_response_hash_total = 0
    parity_pair_total = 0
    parity_mismatch_total = 0
    non_deterministic_total = 0

    by_scenario_mode: dict[tuple[str, str], set[str]] = {}
    by_seed_mode: dict[tuple[str, str], set[str]] = {}

    for row in rows:
        run_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        scenario_id = str(row.get("scenario_id") or row.get("run_id") or "").strip()
        mode = _normalize_mode(row.get("mode") or row.get("runtime_mode"))
        result = _normalize_result(row.get("result") or row.get("status"))
        seed = str(row.get("seed") or row.get("replay_seed") or "").strip()
        response_hash = str(row.get("response_hash") or row.get("result_hash") or "").strip()

        if mode == "MOCK":
            mock_total += 1
        elif mode == "REAL":
            real_total += 1
        else:
            missing_mode_total += 1

        if result not in VALID_RESULTS:
            invalid_result_total += 1
        if not seed:
            missing_seed_total += 1
        if not response_hash:
            missing_response_hash_total += 1

        if scenario_id and mode in VALID_MODES and response_hash:
            key = (scenario_id, mode)
            by_scenario_mode.setdefault(key, set()).add(response_hash)
        if seed and mode in VALID_MODES and response_hash:
            seed_key = (seed, mode)
            by_seed_mode.setdefault(seed_key, set()).add(response_hash)

    scenario_ids = {scenario_id for (scenario_id, _mode) in by_scenario_mode.keys()}
    for scenario_id in scenario_ids:
        mock_hashes = by_scenario_mode.get((scenario_id, "MOCK"))
        real_hashes = by_scenario_mode.get((scenario_id, "REAL"))
        if not mock_hashes or not real_hashes:
            continue
        parity_pair_total += 1
        if mock_hashes.isdisjoint(real_hashes):
            parity_mismatch_total += 1

    for hashes in by_seed_mode.values():
        if len(hashes) > 1:
            non_deterministic_total += 1

    parity_match_ratio = (
        1.0 if parity_pair_total == 0 else float(parity_pair_total - parity_mismatch_total) / float(parity_pair_total)
    )
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "run_total": run_total,
        "mock_total": mock_total,
        "real_total": real_total,
        "missing_mode_total": missing_mode_total,
        "invalid_result_total": invalid_result_total,
        "missing_seed_total": missing_seed_total,
        "missing_response_hash_total": missing_response_hash_total,
        "parity_pair_total": parity_pair_total,
        "parity_mismatch_total": parity_mismatch_total,
        "parity_match_ratio": parity_match_ratio,
        "non_deterministic_total": non_deterministic_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_mock_total: int,
    min_real_total: int,
    max_parity_mismatch_total: int,
    max_non_deterministic_total: int,
    max_missing_mode_total: int,
    max_invalid_result_total: int,
    max_missing_seed_total: int,
    max_missing_response_hash_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    mock_total = _safe_int(summary.get("mock_total"), 0)
    real_total = _safe_int(summary.get("real_total"), 0)
    parity_mismatch_total = _safe_int(summary.get("parity_mismatch_total"), 0)
    non_deterministic_total = _safe_int(summary.get("non_deterministic_total"), 0)
    missing_mode_total = _safe_int(summary.get("missing_mode_total"), 0)
    invalid_result_total = _safe_int(summary.get("invalid_result_total"), 0)
    missing_seed_total = _safe_int(summary.get("missing_seed_total"), 0)
    missing_response_hash_total = _safe_int(summary.get("missing_response_hash_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"replay sandbox runtime window too small: {window_size} < {int(min_window)}")
    if mock_total < max(0, int(min_mock_total)):
        failures.append(f"replay sandbox mock total too small: {mock_total} < {int(min_mock_total)}")
    if real_total < max(0, int(min_real_total)):
        failures.append(f"replay sandbox real total too small: {real_total} < {int(min_real_total)}")
    if window_size == 0:
        return failures

    if parity_mismatch_total > max(0, int(max_parity_mismatch_total)):
        failures.append(f"replay sandbox parity mismatch total exceeded: {parity_mismatch_total} > {int(max_parity_mismatch_total)}")
    if non_deterministic_total > max(0, int(max_non_deterministic_total)):
        failures.append(
            f"replay sandbox non-deterministic seed total exceeded: {non_deterministic_total} > {int(max_non_deterministic_total)}"
        )
    if missing_mode_total > max(0, int(max_missing_mode_total)):
        failures.append(f"replay sandbox missing mode total exceeded: {missing_mode_total} > {int(max_missing_mode_total)}")
    if invalid_result_total > max(0, int(max_invalid_result_total)):
        failures.append(f"replay sandbox invalid result total exceeded: {invalid_result_total} > {int(max_invalid_result_total)}")
    if missing_seed_total > max(0, int(max_missing_seed_total)):
        failures.append(f"replay sandbox missing seed total exceeded: {missing_seed_total} > {int(max_missing_seed_total)}")
    if missing_response_hash_total > max(0, int(max_missing_response_hash_total)):
        failures.append(
            f"replay sandbox missing response hash total exceeded: {missing_response_hash_total} > {int(max_missing_response_hash_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"replay sandbox runtime stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Replay Sandbox Runtime")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- mock_total: {_safe_int(summary.get('mock_total'), 0)}")
    lines.append(f"- real_total: {_safe_int(summary.get('real_total'), 0)}")
    lines.append(f"- parity_mismatch_total: {_safe_int(summary.get('parity_mismatch_total'), 0)}")
    lines.append(f"- non_deterministic_total: {_safe_int(summary.get('non_deterministic_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate deterministic replay sandbox runtime behavior.")
    parser.add_argument("--events-jsonl", default="var/chat_graph/replay/sandbox_runs.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_replay_sandbox_runtime")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-mock-total", type=int, default=0)
    parser.add_argument("--min-real-total", type=int, default=0)
    parser.add_argument("--max-parity-mismatch-total", type=int, default=0)
    parser.add_argument("--max-non-deterministic-total", type=int, default=0)
    parser.add_argument("--max-missing-mode-total", type=int, default=0)
    parser.add_argument("--max-invalid-result-total", type=int, default=0)
    parser.add_argument("--max-missing-seed-total", type=int, default=0)
    parser.add_argument("--max-missing-response-hash-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_sandbox_runtime(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_mock_total=max(0, int(args.min_mock_total)),
        min_real_total=max(0, int(args.min_real_total)),
        max_parity_mismatch_total=max(0, int(args.max_parity_mismatch_total)),
        max_non_deterministic_total=max(0, int(args.max_non_deterministic_total)),
        max_missing_mode_total=max(0, int(args.max_missing_mode_total)),
        max_invalid_result_total=max(0, int(args.max_invalid_result_total)),
        max_missing_seed_total=max(0, int(args.max_missing_seed_total)),
        max_missing_response_hash_total=max(0, int(args.max_missing_response_hash_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events_jsonl": str(args.events_jsonl),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "min_mock_total": int(args.min_mock_total),
                "min_real_total": int(args.min_real_total),
                "max_parity_mismatch_total": int(args.max_parity_mismatch_total),
                "max_non_deterministic_total": int(args.max_non_deterministic_total),
                "max_missing_mode_total": int(args.max_missing_mode_total),
                "max_invalid_result_total": int(args.max_invalid_result_total),
                "max_missing_seed_total": int(args.max_missing_seed_total),
                "max_missing_response_hash_total": int(args.max_missing_response_hash_total),
                "max_stale_minutes": float(args.max_stale_minutes),
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
    print(f"mock_total={_safe_int(summary.get('mock_total'), 0)}")
    print(f"real_total={_safe_int(summary.get('real_total'), 0)}")
    print(f"parity_mismatch_total={_safe_int(summary.get('parity_mismatch_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
