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


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return None


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


def _claim_has_evidence(claim: Mapping[str, Any]) -> bool:
    for key in ("evidence_ids", "source_ids", "citations"):
        value = claim.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
    snippet = str(claim.get("evidence_snippet") or claim.get("snippet") or "").strip()
    source = str(claim.get("source") or claim.get("source_id") or "").strip()
    return bool(snippet and source)


def summarize_grounded_answer_composer_guard(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    response_total = 0
    claim_total = 0
    grounded_claim_total = 0
    ungrounded_claim_total = 0
    response_with_ungrounded_total = 0
    ungrounded_exposed_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        response_total += 1
        row_claim_total = 0
        row_grounded_total = 0
        row_ungrounded_total = 0
        row_ungrounded_exposed = 0

        claims = row.get("claims")
        if isinstance(claims, list) and claims:
            for claim in claims:
                if not isinstance(claim, Mapping):
                    continue
                row_claim_total += 1
                grounded = _claim_has_evidence(claim)
                if grounded:
                    row_grounded_total += 1
                else:
                    row_ungrounded_total += 1
                    included = _safe_bool(claim.get("included_in_output"))
                    if included is not False:
                        row_ungrounded_exposed += 1
        else:
            row_claim_total = max(0, _safe_int(row.get("claim_total") or row.get("claims_total"), 0))
            row_grounded_total = max(
                0, _safe_int(row.get("grounded_claim_total") or row.get("bound_claim_total"), 0)
            )
            row_grounded_total = min(row_claim_total, row_grounded_total)
            row_ungrounded_total = max(0, row_claim_total - row_grounded_total)
            row_ungrounded_exposed = max(
                0, _safe_int(row.get("ungrounded_exposed_claim_total") or row.get("unsupported_claim_total"), 0)
            )

        claim_total += row_claim_total
        grounded_claim_total += row_grounded_total
        ungrounded_claim_total += row_ungrounded_total
        ungrounded_exposed_total += row_ungrounded_exposed
        if row_ungrounded_total > 0:
            response_with_ungrounded_total += 1

    claim_binding_coverage_ratio = 1.0 if claim_total == 0 else float(grounded_claim_total) / float(claim_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "response_total": response_total,
        "claim_total": claim_total,
        "grounded_claim_total": grounded_claim_total,
        "ungrounded_claim_total": ungrounded_claim_total,
        "claim_binding_coverage_ratio": claim_binding_coverage_ratio,
        "response_with_ungrounded_total": response_with_ungrounded_total,
        "ungrounded_exposed_total": ungrounded_exposed_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_response_total: int,
    min_claim_binding_coverage_ratio: float,
    max_response_with_ungrounded_total: int,
    max_ungrounded_exposed_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    response_total = _safe_int(summary.get("response_total"), 0)
    claim_binding_coverage_ratio = _safe_float(summary.get("claim_binding_coverage_ratio"), 0.0)
    response_with_ungrounded_total = _safe_int(summary.get("response_with_ungrounded_total"), 0)
    ungrounded_exposed_total = _safe_int(summary.get("ungrounded_exposed_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"grounded answer window too small: {window_size} < {int(min_window)}")
    if response_total < max(0, int(min_response_total)):
        failures.append(f"grounded answer response total too small: {response_total} < {int(min_response_total)}")
    if window_size == 0:
        return failures

    if claim_binding_coverage_ratio < max(0.0, float(min_claim_binding_coverage_ratio)):
        failures.append(
            "grounded answer claim binding coverage below minimum: "
            f"{claim_binding_coverage_ratio:.4f} < {float(min_claim_binding_coverage_ratio):.4f}"
        )
    if response_with_ungrounded_total > max(0, int(max_response_with_ungrounded_total)):
        failures.append(
            "grounded answer responses-with-ungrounded total exceeded: "
            f"{response_with_ungrounded_total} > {int(max_response_with_ungrounded_total)}"
        )
    if ungrounded_exposed_total > max(0, int(max_ungrounded_exposed_total)):
        failures.append(
            f"grounded answer ungrounded-exposed total exceeded: {ungrounded_exposed_total} > {int(max_ungrounded_exposed_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"grounded answer stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Grounded Answer Composer Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- response_total: {_safe_int(summary.get('response_total'), 0)}")
    lines.append(f"- claim_total: {_safe_int(summary.get('claim_total'), 0)}")
    lines.append(f"- claim_binding_coverage_ratio: {_safe_float(summary.get('claim_binding_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- ungrounded_exposed_total: {_safe_int(summary.get('ungrounded_exposed_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate grounded answer composer quality.")
    parser.add_argument("--events-jsonl", default="var/grounded_answer/composer_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_grounded_answer_composer_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-response-total", type=int, default=0)
    parser.add_argument("--min-claim-binding-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-response-with-ungrounded-total", type=int, default=1000000)
    parser.add_argument("--max-ungrounded-exposed-total", type=int, default=1000000)
    parser.add_argument("--max-stale-minutes", type=float, default=1000000.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.events_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_grounded_answer_composer_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_response_total=max(0, int(args.min_response_total)),
        min_claim_binding_coverage_ratio=max(0.0, float(args.min_claim_binding_coverage_ratio)),
        max_response_with_ungrounded_total=max(0, int(args.max_response_with_ungrounded_total)),
        max_ungrounded_exposed_total=max(0, int(args.max_ungrounded_exposed_total)),
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
                "min_response_total": int(args.min_response_total),
                "min_claim_binding_coverage_ratio": float(args.min_claim_binding_coverage_ratio),
                "max_response_with_ungrounded_total": int(args.max_response_with_ungrounded_total),
                "max_ungrounded_exposed_total": int(args.max_ungrounded_exposed_total),
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
    print(f"response_total={_safe_int(summary.get('response_total'), 0)}")
    print(f"claim_binding_coverage_ratio={_safe_float(summary.get('claim_binding_coverage_ratio'), 0.0):.4f}")
    print(f"ungrounded_exposed_total={_safe_int(summary.get('ungrounded_exposed_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
