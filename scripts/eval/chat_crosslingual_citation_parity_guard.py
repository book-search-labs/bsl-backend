#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


CONTRADICTION_LABELS = {"CONTRADICTION", "MISMATCH", "NOT_ENTAILED", "UNSUPPORTED"}


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


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()


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


def _has_citation(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("has_citation"), False):
        return True
    return bool(str(row.get("citation_id") or row.get("source_doc_id") or row.get("doc_id") or "").strip())


def _citation_parity_pass(row: Mapping[str, Any], *, min_alignment_score: float) -> bool:
    if "citation_parity_pass" in row:
        return _safe_bool(row.get("citation_parity_pass"), False)
    if _safe_bool(row.get("citation_mismatch"), False):
        return False
    entailment = _normalize_token(row.get("entailment_label") or row.get("xlingual_entailment"))
    if entailment and entailment in CONTRADICTION_LABELS:
        return False
    alignment_score = _safe_float(row.get("citation_alignment_score"), 1.0)
    if alignment_score < float(min_alignment_score):
        return False
    if not _has_citation(row):
        return False
    return True


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("mismatch_reason_code") or "").strip())


def summarize_crosslingual_citation_parity_guard(
    rows: list[Mapping[str, Any]],
    *,
    min_alignment_score: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    claim_total = 0
    cited_claim_total = 0
    citation_parity_pass_total = 0
    citation_mismatch_total = 0
    missing_citation_total = 0
    entailment_mismatch_total = 0
    reason_code_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        claim_id = str(row.get("claim_id") or row.get("answer_claim_id") or "").strip()
        claim_text = str(row.get("claim_text") or row.get("translated_claim") or row.get("claim") or "").strip()
        if not claim_id and not claim_text:
            continue

        claim_total += 1
        has_citation = _has_citation(row)
        if has_citation:
            cited_claim_total += 1
        else:
            missing_citation_total += 1

        entailment = _normalize_token(row.get("entailment_label") or row.get("xlingual_entailment"))
        if entailment in CONTRADICTION_LABELS:
            entailment_mismatch_total += 1

        parity_pass = _citation_parity_pass(row, min_alignment_score=min_alignment_score)
        if parity_pass:
            citation_parity_pass_total += 1
        else:
            citation_mismatch_total += 1
            if not _reason_present(row):
                reason_code_missing_total += 1

    citation_parity_ratio = 1.0 if cited_claim_total == 0 else float(citation_parity_pass_total) / float(cited_claim_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "claim_total": claim_total,
        "cited_claim_total": cited_claim_total,
        "citation_parity_pass_total": citation_parity_pass_total,
        "citation_parity_ratio": citation_parity_ratio,
        "citation_mismatch_total": citation_mismatch_total,
        "missing_citation_total": missing_citation_total,
        "entailment_mismatch_total": entailment_mismatch_total,
        "reason_code_missing_total": reason_code_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_claim_total: int,
    min_citation_parity_ratio: float,
    max_citation_mismatch_total: int,
    max_missing_citation_total: int,
    max_entailment_mismatch_total: int,
    max_reason_code_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    claim_total = _safe_int(summary.get("claim_total"), 0)
    citation_parity_ratio = _safe_float(summary.get("citation_parity_ratio"), 0.0)
    citation_mismatch_total = _safe_int(summary.get("citation_mismatch_total"), 0)
    missing_citation_total = _safe_int(summary.get("missing_citation_total"), 0)
    entailment_mismatch_total = _safe_int(summary.get("entailment_mismatch_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"crosslingual citation parity window too small: {window_size} < {int(min_window)}")
    if claim_total < max(0, int(min_claim_total)):
        failures.append(f"crosslingual citation parity claim total too small: {claim_total} < {int(min_claim_total)}")
    if window_size == 0:
        return failures

    if citation_parity_ratio < max(0.0, float(min_citation_parity_ratio)):
        failures.append(
            f"crosslingual citation parity ratio below minimum: {citation_parity_ratio:.4f} < {float(min_citation_parity_ratio):.4f}"
        )
    if citation_mismatch_total > max(0, int(max_citation_mismatch_total)):
        failures.append(
            f"crosslingual citation mismatch total exceeded: {citation_mismatch_total} > {int(max_citation_mismatch_total)}"
        )
    if missing_citation_total > max(0, int(max_missing_citation_total)):
        failures.append(
            f"crosslingual missing citation total exceeded: {missing_citation_total} > {int(max_missing_citation_total)}"
        )
    if entailment_mismatch_total > max(0, int(max_entailment_mismatch_total)):
        failures.append(
            f"crosslingual entailment mismatch total exceeded: {entailment_mismatch_total} > {int(max_entailment_mismatch_total)}"
        )
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"crosslingual citation reason code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"crosslingual citation parity stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Cross-lingual Citation Parity Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- claim_total: {_safe_int(summary.get('claim_total'), 0)}")
    lines.append(f"- citation_parity_ratio: {_safe_float(summary.get('citation_parity_ratio'), 0.0):.4f}")
    lines.append(f"- citation_mismatch_total: {_safe_int(summary.get('citation_mismatch_total'), 0)}")
    lines.append(f"- entailment_mismatch_total: {_safe_int(summary.get('entailment_mismatch_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate citation parity between translated/re-written claims and source evidence.")
    parser.add_argument("--events-jsonl", default="var/crosslingual/citation_parity_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_crosslingual_citation_parity_guard")
    parser.add_argument("--min-alignment-score", type=float, default=0.7)
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-claim-total", type=int, default=0)
    parser.add_argument("--min-citation-parity-ratio", type=float, default=0.0)
    parser.add_argument("--max-citation-mismatch-total", type=int, default=1000000)
    parser.add_argument("--max-missing-citation-total", type=int, default=1000000)
    parser.add_argument("--max-entailment-mismatch-total", type=int, default=1000000)
    parser.add_argument("--max-reason-code-missing-total", type=int, default=1000000)
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
    summary = summarize_crosslingual_citation_parity_guard(
        rows,
        min_alignment_score=max(0.0, min(1.0, float(args.min_alignment_score))),
    )
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_claim_total=max(0, int(args.min_claim_total)),
        min_citation_parity_ratio=max(0.0, float(args.min_citation_parity_ratio)),
        max_citation_mismatch_total=max(0, int(args.max_citation_mismatch_total)),
        max_missing_citation_total=max(0, int(args.max_missing_citation_total)),
        max_entailment_mismatch_total=max(0, int(args.max_entailment_mismatch_total)),
        max_reason_code_missing_total=max(0, int(args.max_reason_code_missing_total)),
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
                "min_alignment_score": float(args.min_alignment_score),
                "min_window": int(args.min_window),
                "min_claim_total": int(args.min_claim_total),
                "min_citation_parity_ratio": float(args.min_citation_parity_ratio),
                "max_citation_mismatch_total": int(args.max_citation_mismatch_total),
                "max_missing_citation_total": int(args.max_missing_citation_total),
                "max_entailment_mismatch_total": int(args.max_entailment_mismatch_total),
                "max_reason_code_missing_total": int(args.max_reason_code_missing_total),
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
    print(f"citation_parity_ratio={_safe_float(summary.get('citation_parity_ratio'), 0.0):.4f}")
    print(f"citation_mismatch_total={_safe_int(summary.get('citation_mismatch_total'), 0)}")
    print(f"entailment_mismatch_total={_safe_int(summary.get('entailment_mismatch_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
