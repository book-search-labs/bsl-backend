#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

MISMATCH_VERDICTS = {"MISMATCH", "CONTRADICTED", "CONTRADICTION"}
UNSUPPORTED_VERDICTS = {"UNSUPPORTED", "NO_EVIDENCE", "INSUFFICIENT_EVIDENCE"}


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
    for key in ("timestamp", "event_time", "created_at", "updated_at", "verified_at", "generated_at"):
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


def _verdict(row: Mapping[str, Any]) -> str:
    return str(row.get("verdict") or row.get("claim_verdict") or row.get("entailment_verdict") or "").strip().upper()


def _verified(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("claim_verified"), False) or _safe_bool(row.get("verifier_checked"), False):
        return True
    return bool(_verdict(row))


def _mismatch(row: Mapping[str, Any], verdict: str) -> bool:
    if _safe_bool(row.get("mismatch_detected"), False):
        return True
    return verdict in MISMATCH_VERDICTS


def _unsupported(row: Mapping[str, Any], verdict: str) -> bool:
    if _safe_bool(row.get("unsupported_detected"), False):
        return True
    return verdict in UNSUPPORTED_VERDICTS


def _missing_evidence_refs(row: Mapping[str, Any]) -> bool:
    refs = row.get("evidence_refs") or row.get("citations") or row.get("evidence_ids")
    if refs is None:
        return True
    if isinstance(refs, list):
        return len(refs) == 0
    text = str(refs).strip()
    return not text


def _mitigated(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("claim_removed"), False) or _safe_bool(row.get("abstained"), False):
        return True
    action = str(row.get("mitigation_action") or row.get("response_action") or "").strip().upper()
    return action in {"AUTO_REMOVE", "REMOVE", "ABSTAIN", "DOWNGRADE"}


def _latency_ms(row: Mapping[str, Any]) -> float:
    value = row.get("verifier_latency_ms")
    if value is not None:
        return max(0.0, _safe_float(value, 0.0))
    seconds = row.get("verifier_latency_sec")
    if seconds is not None:
        return max(0.0, _safe_float(seconds, 0.0) * 1000.0)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_claim_verifier_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    claim_total = 0
    verified_claim_total = 0
    mismatch_total = 0
    unsupported_total = 0
    mismatch_mitigated_total = 0
    missing_evidence_ref_total = 0
    latency_samples: list[float] = []

    for row in rows:
        claim_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _verified(row):
            continue
        verified_claim_total += 1
        latency_samples.append(_latency_ms(row))

        verdict = _verdict(row)
        mismatch = _mismatch(row, verdict)
        unsupported = _unsupported(row, verdict)
        if mismatch:
            mismatch_total += 1
            if _mitigated(row):
                mismatch_mitigated_total += 1
        if unsupported:
            unsupported_total += 1
        if _missing_evidence_refs(row):
            missing_evidence_ref_total += 1

    verifier_coverage_ratio = 1.0 if claim_total == 0 else float(verified_claim_total) / float(claim_total)
    mismatch_ratio = 0.0 if verified_claim_total == 0 else float(mismatch_total) / float(verified_claim_total)
    mismatch_mitigated_ratio = 1.0 if mismatch_total == 0 else float(mismatch_mitigated_total) / float(mismatch_total)
    p95_verifier_latency_ms = _p95(latency_samples)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "claim_total": claim_total,
        "verified_claim_total": verified_claim_total,
        "verifier_coverage_ratio": verifier_coverage_ratio,
        "mismatch_total": mismatch_total,
        "mismatch_ratio": mismatch_ratio,
        "unsupported_total": unsupported_total,
        "mismatch_mitigated_total": mismatch_mitigated_total,
        "mismatch_mitigated_ratio": mismatch_mitigated_ratio,
        "missing_evidence_ref_total": missing_evidence_ref_total,
        "p95_verifier_latency_ms": p95_verifier_latency_ms,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_claim_total: int,
    min_verifier_coverage_ratio: float,
    max_mismatch_ratio: float,
    max_unsupported_total: int,
    min_mismatch_mitigated_ratio: float,
    max_missing_evidence_ref_total: int,
    max_p95_verifier_latency_ms: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    claim_total = _safe_int(summary.get("claim_total"), 0)
    verifier_coverage_ratio = _safe_float(summary.get("verifier_coverage_ratio"), 0.0)
    mismatch_ratio = _safe_float(summary.get("mismatch_ratio"), 0.0)
    unsupported_total = _safe_int(summary.get("unsupported_total"), 0)
    mismatch_mitigated_ratio = _safe_float(summary.get("mismatch_mitigated_ratio"), 1.0)
    missing_evidence_ref_total = _safe_int(summary.get("missing_evidence_ref_total"), 0)
    p95_verifier_latency_ms = _safe_float(summary.get("p95_verifier_latency_ms"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat claim verifier window too small: {window_size} < {int(min_window)}")
    if claim_total < max(0, int(min_claim_total)):
        failures.append(f"chat claim total too small: {claim_total} < {int(min_claim_total)}")
    if window_size == 0:
        return failures

    if verifier_coverage_ratio < max(0.0, float(min_verifier_coverage_ratio)):
        failures.append(
            "chat claim verifier coverage ratio below minimum: "
            f"{verifier_coverage_ratio:.4f} < {float(min_verifier_coverage_ratio):.4f}"
        )
    if mismatch_ratio > max(0.0, float(max_mismatch_ratio)):
        failures.append(f"chat claim mismatch ratio exceeded: {mismatch_ratio:.4f} > {float(max_mismatch_ratio):.4f}")
    if unsupported_total > max(0, int(max_unsupported_total)):
        failures.append(f"chat claim unsupported total exceeded: {unsupported_total} > {int(max_unsupported_total)}")
    if mismatch_mitigated_ratio < max(0.0, float(min_mismatch_mitigated_ratio)):
        failures.append(
            "chat claim mismatch mitigated ratio below minimum: "
            f"{mismatch_mitigated_ratio:.4f} < {float(min_mismatch_mitigated_ratio):.4f}"
        )
    if missing_evidence_ref_total > max(0, int(max_missing_evidence_ref_total)):
        failures.append(
            "chat claim missing evidence refs total exceeded: "
            f"{missing_evidence_ref_total} > {int(max_missing_evidence_ref_total)}"
        )
    if p95_verifier_latency_ms > max(0.0, float(max_p95_verifier_latency_ms)):
        failures.append(
            f"chat claim verifier p95 latency exceeded: {p95_verifier_latency_ms:.2f}ms > {float(max_p95_verifier_latency_ms):.2f}ms"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat claim verifier stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Claim Verifier Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- claim_total: {_safe_int(summary.get('claim_total'), 0)}")
    lines.append(f"- verifier_coverage_ratio: {_safe_float(summary.get('verifier_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- mismatch_ratio: {_safe_float(summary.get('mismatch_ratio'), 0.0):.4f}")
    lines.append(f"- mismatch_mitigated_ratio: {_safe_float(summary.get('mismatch_mitigated_ratio'), 1.0):.4f}")
    lines.append(f"- missing_evidence_ref_total: {_safe_int(summary.get('missing_evidence_ref_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat claim verifier quality.")
    parser.add_argument("--events-jsonl", default="var/chat_output_guard/claim_verifier_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_claim_verifier_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-claim-total", type=int, default=0)
    parser.add_argument("--min-verifier-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--max-mismatch-ratio", type=float, default=1.0)
    parser.add_argument("--max-unsupported-total", type=int, default=0)
    parser.add_argument("--min-mismatch-mitigated-ratio", type=float, default=0.0)
    parser.add_argument("--max-missing-evidence-ref-total", type=int, default=0)
    parser.add_argument("--max-p95-verifier-latency-ms", type=float, default=1000000.0)
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
    summary = summarize_claim_verifier_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_claim_total=max(0, int(args.min_claim_total)),
        min_verifier_coverage_ratio=max(0.0, float(args.min_verifier_coverage_ratio)),
        max_mismatch_ratio=max(0.0, float(args.max_mismatch_ratio)),
        max_unsupported_total=max(0, int(args.max_unsupported_total)),
        min_mismatch_mitigated_ratio=max(0.0, float(args.min_mismatch_mitigated_ratio)),
        max_missing_evidence_ref_total=max(0, int(args.max_missing_evidence_ref_total)),
        max_p95_verifier_latency_ms=max(0.0, float(args.max_p95_verifier_latency_ms)),
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
                "min_claim_total": int(args.min_claim_total),
                "min_verifier_coverage_ratio": float(args.min_verifier_coverage_ratio),
                "max_mismatch_ratio": float(args.max_mismatch_ratio),
                "max_unsupported_total": int(args.max_unsupported_total),
                "min_mismatch_mitigated_ratio": float(args.min_mismatch_mitigated_ratio),
                "max_missing_evidence_ref_total": int(args.max_missing_evidence_ref_total),
                "max_p95_verifier_latency_ms": float(args.max_p95_verifier_latency_ms),
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
    print(f"claim_total={_safe_int(summary.get('claim_total'), 0)}")
    print(f"mismatch_total={_safe_int(summary.get('mismatch_total'), 0)}")
    print(f"missing_evidence_ref_total={_safe_int(summary.get('missing_evidence_ref_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
