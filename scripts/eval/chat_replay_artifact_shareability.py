#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

INVALID_SHARE_SCOPES = {"PUBLIC", "EXTERNAL", "ANONYMOUS"}
SENSITIVE_PATTERNS = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b(?:\+?\d{1,3}[- ]?)?(?:\d{2,4}[- ]?){2,4}\d{2,4}\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
)
MASKING_TOKENS = ("***", "[REDACTED]", "<REDACTED>", "masked", "redacted", "xxxx")


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


def _flatten_text(value: Any, sink: list[str], depth: int = 0) -> None:
    if depth > 3:
        return
    if isinstance(value, str):
        if value:
            sink.append(value)
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _flatten_text(item, sink, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _flatten_text(item, sink, depth + 1)
        return
    if isinstance(value, (int, float)):
        sink.append(str(value))


def _row_text_blob(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "summary",
        "note",
        "payload",
        "artifact_payload",
        "request_payload",
        "response_payload",
        "tool_io",
        "messages",
        "user_message",
        "assistant_message",
        "contact",
        "shipping_address",
        "billing_address",
    ):
        if key in row:
            _flatten_text(row.get(key), parts)
    if not parts:
        _flatten_text(row, parts)
    return "\n".join(parts)


def _has_masking_token(text: str) -> bool:
    lowered = text.lower()
    for token in MASKING_TOKENS:
        if token.lower() in lowered:
            return True
    return False


def _contains_sensitive_pattern(text: str) -> bool:
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _status(row: Mapping[str, Any]) -> str:
    return str(row.get("status") or row.get("result") or "").strip().upper()


def _artifact_exists(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("artifact_created"), False):
        return True
    status = _status(row)
    if status in {"CREATED", "READY", "UPLOADED", "GENERATED", "SHARED"}:
        return True
    for key in ("artifact_id", "artifact_path", "bundle_path", "artifact_url", "share_url", "download_url"):
        if str(row.get(key) or "").strip():
            return True
    return False


def _is_shareable(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("shareable"), False):
        return True
    status = _status(row)
    if status in {"SHARED", "PUBLISHED"}:
        return True
    for key in ("share_url", "artifact_url", "download_url", "bundle_path", "artifact_path"):
        if str(row.get(key) or "").strip():
            return True
    return False


def _ticket_reference(row: Mapping[str, Any]) -> str:
    for key in ("ticket_id", "ticket_ref", "incident_id", "rca_id", "jira_issue", "case_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _share_scope(row: Mapping[str, Any]) -> str:
    for key in ("share_scope", "access_scope", "visibility"):
        value = str(row.get(key) or "").strip().upper()
        if value:
            return value
    return ""


def _redaction_applied(row: Mapping[str, Any], text_blob: str) -> bool:
    if _safe_bool(row.get("redaction_applied"), False):
        return True
    if _safe_bool(row.get("masked"), False):
        return True
    if _safe_bool(row.get("pii_masked"), False):
        return True
    redaction = row.get("redaction")
    if isinstance(redaction, Mapping):
        if _safe_bool(redaction.get("applied"), False):
            return True
        if _safe_int(redaction.get("masked_fields"), 0) > 0:
            return True
    if _has_masking_token(text_blob):
        return True
    return False


def summarize_artifact_shareability(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    run_total = 0
    artifact_created_total = 0
    shareable_total = 0
    redaction_applied_total = 0
    missing_redaction_total = 0
    unmasked_sensitive_total = 0
    missing_ticket_reference_total = 0
    invalid_share_scope_total = 0

    for row in rows:
        run_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _artifact_exists(row):
            continue
        artifact_created_total += 1

        shareable = _is_shareable(row)
        if shareable:
            shareable_total += 1

        text_blob = _row_text_blob(row)
        redaction_applied = _redaction_applied(row, text_blob)
        if redaction_applied:
            redaction_applied_total += 1
        else:
            missing_redaction_total += 1

        if _contains_sensitive_pattern(text_blob) and not redaction_applied:
            unmasked_sensitive_total += 1

        if not _ticket_reference(row):
            missing_ticket_reference_total += 1

        share_scope = _share_scope(row)
        if shareable and share_scope in INVALID_SHARE_SCOPES:
            invalid_share_scope_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)
    redaction_ratio = (
        1.0 if artifact_created_total == 0 else float(redaction_applied_total) / float(max(1, artifact_created_total))
    )

    return {
        "window_size": len(rows),
        "run_total": run_total,
        "artifact_created_total": artifact_created_total,
        "shareable_total": shareable_total,
        "redaction_applied_total": redaction_applied_total,
        "redaction_ratio": redaction_ratio,
        "missing_redaction_total": missing_redaction_total,
        "unmasked_sensitive_total": unmasked_sensitive_total,
        "missing_ticket_reference_total": missing_ticket_reference_total,
        "invalid_share_scope_total": invalid_share_scope_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_artifact_created_total: int,
    min_shareable_total: int,
    max_missing_redaction_total: int,
    max_unmasked_sensitive_total: int,
    max_missing_ticket_reference_total: int,
    max_invalid_share_scope_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    artifact_created_total = _safe_int(summary.get("artifact_created_total"), 0)
    shareable_total = _safe_int(summary.get("shareable_total"), 0)
    missing_redaction_total = _safe_int(summary.get("missing_redaction_total"), 0)
    unmasked_sensitive_total = _safe_int(summary.get("unmasked_sensitive_total"), 0)
    missing_ticket_reference_total = _safe_int(summary.get("missing_ticket_reference_total"), 0)
    invalid_share_scope_total = _safe_int(summary.get("invalid_share_scope_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"replay artifact window too small: {window_size} < {int(min_window)}")
    if artifact_created_total < max(0, int(min_artifact_created_total)):
        failures.append(
            f"replay artifact created total too small: {artifact_created_total} < {int(min_artifact_created_total)}"
        )
    if shareable_total < max(0, int(min_shareable_total)):
        failures.append(f"replay artifact shareable total too small: {shareable_total} < {int(min_shareable_total)}")
    if window_size == 0:
        return failures

    if missing_redaction_total > max(0, int(max_missing_redaction_total)):
        failures.append(
            f"replay artifact missing redaction total exceeded: {missing_redaction_total} > {int(max_missing_redaction_total)}"
        )
    if unmasked_sensitive_total > max(0, int(max_unmasked_sensitive_total)):
        failures.append(
            f"replay artifact unmasked sensitive total exceeded: {unmasked_sensitive_total} > {int(max_unmasked_sensitive_total)}"
        )
    if missing_ticket_reference_total > max(0, int(max_missing_ticket_reference_total)):
        failures.append(
            "replay artifact missing ticket reference total exceeded: "
            f"{missing_ticket_reference_total} > {int(max_missing_ticket_reference_total)}"
        )
    if invalid_share_scope_total > max(0, int(max_invalid_share_scope_total)):
        failures.append(
            f"replay artifact invalid share scope total exceeded: {invalid_share_scope_total} > {int(max_invalid_share_scope_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"replay artifact shareability stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_artifact_created_total_drop: int,
    max_shareable_total_drop: int,
    max_redaction_applied_total_drop: int,
    max_missing_redaction_total_increase: int,
    max_unmasked_sensitive_total_increase: int,
    max_missing_ticket_reference_total_increase: int,
    max_invalid_share_scope_total_increase: int,
    max_redaction_ratio_drop: float,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    baseline_drop_pairs = [
        ("artifact_created_total", max_artifact_created_total_drop),
        ("shareable_total", max_shareable_total_drop),
        ("redaction_applied_total", max_redaction_applied_total_drop),
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

    baseline_increase_pairs = [
        ("missing_redaction_total", max_missing_redaction_total_increase),
        ("unmasked_sensitive_total", max_unmasked_sensitive_total_increase),
        ("missing_ticket_reference_total", max_missing_ticket_reference_total_increase),
        ("invalid_share_scope_total", max_invalid_share_scope_total_increase),
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

    base_redaction_ratio = _safe_float(base_summary.get("redaction_ratio"), 1.0)
    cur_redaction_ratio = _safe_float(current_summary.get("redaction_ratio"), 1.0)
    redaction_ratio_drop = max(0.0, base_redaction_ratio - cur_redaction_ratio)
    if redaction_ratio_drop > max(0.0, float(max_redaction_ratio_drop)):
        failures.append(
            "redaction_ratio regression: "
            f"baseline={base_redaction_ratio:.6f}, current={cur_redaction_ratio:.6f}, "
            f"allowed_drop={float(max_redaction_ratio_drop):.6f}"
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
    lines.append("# Chat Replay Artifact Shareability")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- artifact_created_total: {_safe_int(summary.get('artifact_created_total'), 0)}")
    lines.append(f"- shareable_total: {_safe_int(summary.get('shareable_total'), 0)}")
    lines.append(f"- redaction_applied_total: {_safe_int(summary.get('redaction_applied_total'), 0)}")
    lines.append(f"- missing_redaction_total: {_safe_int(summary.get('missing_redaction_total'), 0)}")
    lines.append(f"- unmasked_sensitive_total: {_safe_int(summary.get('unmasked_sensitive_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate replay artifact shareability and redaction quality.")
    parser.add_argument("--events-jsonl", default="var/chat_graph/replay/artifacts.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_replay_artifact_shareability")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-artifact-created-total", type=int, default=0)
    parser.add_argument("--min-shareable-total", type=int, default=0)
    parser.add_argument("--max-missing-redaction-total", type=int, default=0)
    parser.add_argument("--max-unmasked-sensitive-total", type=int, default=0)
    parser.add_argument("--max-missing-ticket-reference-total", type=int, default=0)
    parser.add_argument("--max-invalid-share-scope-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-artifact-created-total-drop", type=int, default=10)
    parser.add_argument("--max-shareable-total-drop", type=int, default=10)
    parser.add_argument("--max-redaction-applied-total-drop", type=int, default=10)
    parser.add_argument("--max-missing-redaction-total-increase", type=int, default=0)
    parser.add_argument("--max-unmasked-sensitive-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-ticket-reference-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-share-scope-total-increase", type=int, default=0)
    parser.add_argument("--max-redaction-ratio-drop", type=float, default=0.05)
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
    summary = summarize_artifact_shareability(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_artifact_created_total=max(0, int(args.min_artifact_created_total)),
        min_shareable_total=max(0, int(args.min_shareable_total)),
        max_missing_redaction_total=max(0, int(args.max_missing_redaction_total)),
        max_unmasked_sensitive_total=max(0, int(args.max_unmasked_sensitive_total)),
        max_missing_ticket_reference_total=max(0, int(args.max_missing_ticket_reference_total)),
        max_invalid_share_scope_total=max(0, int(args.max_invalid_share_scope_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_artifact_created_total_drop=max(0, int(args.max_artifact_created_total_drop)),
            max_shareable_total_drop=max(0, int(args.max_shareable_total_drop)),
            max_redaction_applied_total_drop=max(0, int(args.max_redaction_applied_total_drop)),
            max_missing_redaction_total_increase=max(0, int(args.max_missing_redaction_total_increase)),
            max_unmasked_sensitive_total_increase=max(0, int(args.max_unmasked_sensitive_total_increase)),
            max_missing_ticket_reference_total_increase=max(0, int(args.max_missing_ticket_reference_total_increase)),
            max_invalid_share_scope_total_increase=max(0, int(args.max_invalid_share_scope_total_increase)),
            max_redaction_ratio_drop=max(0.0, float(args.max_redaction_ratio_drop)),
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
                "min_artifact_created_total": int(args.min_artifact_created_total),
                "min_shareable_total": int(args.min_shareable_total),
                "max_missing_redaction_total": int(args.max_missing_redaction_total),
                "max_unmasked_sensitive_total": int(args.max_unmasked_sensitive_total),
                "max_missing_ticket_reference_total": int(args.max_missing_ticket_reference_total),
                "max_invalid_share_scope_total": int(args.max_invalid_share_scope_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_artifact_created_total_drop": int(args.max_artifact_created_total_drop),
                "max_shareable_total_drop": int(args.max_shareable_total_drop),
                "max_redaction_applied_total_drop": int(args.max_redaction_applied_total_drop),
                "max_missing_redaction_total_increase": int(args.max_missing_redaction_total_increase),
                "max_unmasked_sensitive_total_increase": int(args.max_unmasked_sensitive_total_increase),
                "max_missing_ticket_reference_total_increase": int(args.max_missing_ticket_reference_total_increase),
                "max_invalid_share_scope_total_increase": int(args.max_invalid_share_scope_total_increase),
                "max_redaction_ratio_drop": float(args.max_redaction_ratio_drop),
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
    print(f"artifact_created_total={_safe_int(summary.get('artifact_created_total'), 0)}")
    print(f"missing_redaction_total={_safe_int(summary.get('missing_redaction_total'), 0)}")
    print(f"unmasked_sensitive_total={_safe_int(summary.get('unmasked_sensitive_total'), 0)}")
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")
    if baseline_failures:
        for failure in baseline_failures:
            print(f"baseline_failure={failure}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
