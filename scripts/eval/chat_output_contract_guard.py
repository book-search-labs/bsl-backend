#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

AMOUNT_RE = re.compile(r"^-?\d+(?:\.\d{1,2})?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUS_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


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


def _checked(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("contract_checked"), False) or _safe_bool(row.get("guard_checked"), False):
        return True
    result = str(row.get("guard_result") or row.get("contract_result") or "").strip()
    return bool(result)


def _guard_pass(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("contract_pass"), False) or _safe_bool(row.get("guard_passed"), False):
        return True
    result = str(row.get("guard_result") or row.get("contract_result") or "").strip().upper()
    return result in {"PASS", "ALLOW", "ALLOWED", "OK"}


def _contains_token(value: Any, token: str) -> bool:
    if isinstance(value, list):
        return any(_contains_token(item, token) for item in value)
    text = str(value or "").strip().upper()
    return token in text


def _forbidden_phrase_detected(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("forbidden_phrase_detected"), False) or _safe_bool(row.get("banned_phrase_hit"), False):
        return True
    return _contains_token(row.get("reason_code") or row.get("violation_codes"), "FORBIDDEN_PHRASE")


def _forbidden_action_detected(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("forbidden_action_detected"), False) or _safe_bool(row.get("banned_action_hit"), False):
        return True
    return _contains_token(row.get("reason_code") or row.get("violation_codes"), "FORBIDDEN_ACTION")


def _required_field_missing_count(row: Mapping[str, Any]) -> int:
    if _safe_bool(row.get("required_field_missing"), False):
        return 1
    value = row.get("required_fields_missing")
    if value is None:
        return 0
    if isinstance(value, int):
        return max(0, int(value))
    if isinstance(value, list):
        return len(value)
    text = str(value).strip()
    if not text:
        return 0
    if "," in text:
        return len([item for item in text.split(",") if item.strip()])
    return 1


def _invalid_amount(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("invalid_amount_format"), False):
        return True
    if "amount_format_valid" in row and not _safe_bool(row.get("amount_format_valid"), True):
        return True
    value = row.get("amount") or row.get("response_amount")
    if value is None:
        return False
    text = str(value).replace(",", "").strip()
    return bool(text) and AMOUNT_RE.match(text) is None


def _invalid_date(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("invalid_date_format"), False):
        return True
    if "date_format_valid" in row and not _safe_bool(row.get("date_format_valid"), True):
        return True
    value = row.get("date") or row.get("effective_date") or row.get("response_date")
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if DATE_RE.match(text):
        return False
    parsed = _parse_ts(text)
    return parsed is None


def _invalid_status(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("invalid_status_format"), False):
        return True
    if "status_format_valid" in row and not _safe_bool(row.get("status_format_valid"), True):
        return True
    value = row.get("status") or row.get("response_status")
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    return STATUS_RE.match(text) is None


def summarize_output_contract_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    output_total = 0
    guard_checked_total = 0
    guard_bypass_total = 0
    contract_pass_total = 0
    contract_fail_total = 0
    forbidden_phrase_total = 0
    forbidden_action_total = 0
    required_field_missing_total = 0
    invalid_amount_format_total = 0
    invalid_date_format_total = 0
    invalid_status_format_total = 0

    for row in rows:
        output_total += 1
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        checked = _checked(row)
        if checked:
            guard_checked_total += 1
        else:
            guard_bypass_total += 1

        if _guard_pass(row):
            contract_pass_total += 1
        elif checked:
            contract_fail_total += 1

        if _forbidden_phrase_detected(row):
            forbidden_phrase_total += 1
        if _forbidden_action_detected(row):
            forbidden_action_total += 1
        required_field_missing_total += _required_field_missing_count(row)
        if _invalid_amount(row):
            invalid_amount_format_total += 1
        if _invalid_date(row):
            invalid_date_format_total += 1
        if _invalid_status(row):
            invalid_status_format_total += 1

    guard_coverage_ratio = 1.0 if output_total == 0 else float(guard_checked_total) / float(output_total)
    contract_pass_ratio = 1.0 if guard_checked_total == 0 else float(contract_pass_total) / float(guard_checked_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "output_total": output_total,
        "guard_checked_total": guard_checked_total,
        "guard_bypass_total": guard_bypass_total,
        "contract_pass_total": contract_pass_total,
        "contract_fail_total": contract_fail_total,
        "guard_coverage_ratio": guard_coverage_ratio,
        "contract_pass_ratio": contract_pass_ratio,
        "forbidden_phrase_total": forbidden_phrase_total,
        "forbidden_action_total": forbidden_action_total,
        "required_field_missing_total": required_field_missing_total,
        "invalid_amount_format_total": invalid_amount_format_total,
        "invalid_date_format_total": invalid_date_format_total,
        "invalid_status_format_total": invalid_status_format_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_output_total: int,
    min_guard_coverage_ratio: float,
    min_contract_pass_ratio: float,
    max_guard_bypass_total: int,
    max_forbidden_phrase_total: int,
    max_forbidden_action_total: int,
    max_required_field_missing_total: int,
    max_invalid_amount_format_total: int,
    max_invalid_date_format_total: int,
    max_invalid_status_format_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    output_total = _safe_int(summary.get("output_total"), 0)
    guard_coverage_ratio = _safe_float(summary.get("guard_coverage_ratio"), 0.0)
    contract_pass_ratio = _safe_float(summary.get("contract_pass_ratio"), 0.0)
    guard_bypass_total = _safe_int(summary.get("guard_bypass_total"), 0)
    forbidden_phrase_total = _safe_int(summary.get("forbidden_phrase_total"), 0)
    forbidden_action_total = _safe_int(summary.get("forbidden_action_total"), 0)
    required_field_missing_total = _safe_int(summary.get("required_field_missing_total"), 0)
    invalid_amount_format_total = _safe_int(summary.get("invalid_amount_format_total"), 0)
    invalid_date_format_total = _safe_int(summary.get("invalid_date_format_total"), 0)
    invalid_status_format_total = _safe_int(summary.get("invalid_status_format_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat output contract window too small: {window_size} < {int(min_window)}")
    if output_total < max(0, int(min_output_total)):
        failures.append(f"chat output total too small: {output_total} < {int(min_output_total)}")
    if window_size == 0:
        return failures

    if guard_coverage_ratio < max(0.0, float(min_guard_coverage_ratio)):
        failures.append(
            f"chat output guard coverage ratio below minimum: {guard_coverage_ratio:.4f} < {float(min_guard_coverage_ratio):.4f}"
        )
    if contract_pass_ratio < max(0.0, float(min_contract_pass_ratio)):
        failures.append(
            f"chat output contract pass ratio below minimum: {contract_pass_ratio:.4f} < {float(min_contract_pass_ratio):.4f}"
        )
    if guard_bypass_total > max(0, int(max_guard_bypass_total)):
        failures.append(f"chat output guard bypass total exceeded: {guard_bypass_total} > {int(max_guard_bypass_total)}")
    if forbidden_phrase_total > max(0, int(max_forbidden_phrase_total)):
        failures.append(f"chat output forbidden phrase total exceeded: {forbidden_phrase_total} > {int(max_forbidden_phrase_total)}")
    if forbidden_action_total > max(0, int(max_forbidden_action_total)):
        failures.append(f"chat output forbidden action total exceeded: {forbidden_action_total} > {int(max_forbidden_action_total)}")
    if required_field_missing_total > max(0, int(max_required_field_missing_total)):
        failures.append(
            "chat output required field missing total exceeded: "
            f"{required_field_missing_total} > {int(max_required_field_missing_total)}"
        )
    if invalid_amount_format_total > max(0, int(max_invalid_amount_format_total)):
        failures.append(
            f"chat output invalid amount format total exceeded: {invalid_amount_format_total} > {int(max_invalid_amount_format_total)}"
        )
    if invalid_date_format_total > max(0, int(max_invalid_date_format_total)):
        failures.append(
            f"chat output invalid date format total exceeded: {invalid_date_format_total} > {int(max_invalid_date_format_total)}"
        )
    if invalid_status_format_total > max(0, int(max_invalid_status_format_total)):
        failures.append(
            f"chat output invalid status format total exceeded: {invalid_status_format_total} > {int(max_invalid_status_format_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat output contract stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Output Contract Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- output_total: {_safe_int(summary.get('output_total'), 0)}")
    lines.append(f"- guard_coverage_ratio: {_safe_float(summary.get('guard_coverage_ratio'), 0.0):.4f}")
    lines.append(f"- contract_pass_ratio: {_safe_float(summary.get('contract_pass_ratio'), 0.0):.4f}")
    lines.append(f"- forbidden_phrase_total: {_safe_int(summary.get('forbidden_phrase_total'), 0)}")
    lines.append(f"- forbidden_action_total: {_safe_int(summary.get('forbidden_action_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate chat output contract guard quality.")
    parser.add_argument("--events-jsonl", default="var/chat_output_guard/output_guard_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_output_contract_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-output-total", type=int, default=0)
    parser.add_argument("--min-guard-coverage-ratio", type=float, default=0.0)
    parser.add_argument("--min-contract-pass-ratio", type=float, default=0.0)
    parser.add_argument("--max-guard-bypass-total", type=int, default=0)
    parser.add_argument("--max-forbidden-phrase-total", type=int, default=0)
    parser.add_argument("--max-forbidden-action-total", type=int, default=0)
    parser.add_argument("--max-required-field-missing-total", type=int, default=0)
    parser.add_argument("--max-invalid-amount-format-total", type=int, default=0)
    parser.add_argument("--max-invalid-date-format-total", type=int, default=0)
    parser.add_argument("--max-invalid-status-format-total", type=int, default=0)
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
    summary = summarize_output_contract_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_output_total=max(0, int(args.min_output_total)),
        min_guard_coverage_ratio=max(0.0, float(args.min_guard_coverage_ratio)),
        min_contract_pass_ratio=max(0.0, float(args.min_contract_pass_ratio)),
        max_guard_bypass_total=max(0, int(args.max_guard_bypass_total)),
        max_forbidden_phrase_total=max(0, int(args.max_forbidden_phrase_total)),
        max_forbidden_action_total=max(0, int(args.max_forbidden_action_total)),
        max_required_field_missing_total=max(0, int(args.max_required_field_missing_total)),
        max_invalid_amount_format_total=max(0, int(args.max_invalid_amount_format_total)),
        max_invalid_date_format_total=max(0, int(args.max_invalid_date_format_total)),
        max_invalid_status_format_total=max(0, int(args.max_invalid_status_format_total)),
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
                "min_output_total": int(args.min_output_total),
                "min_guard_coverage_ratio": float(args.min_guard_coverage_ratio),
                "min_contract_pass_ratio": float(args.min_contract_pass_ratio),
                "max_guard_bypass_total": int(args.max_guard_bypass_total),
                "max_forbidden_phrase_total": int(args.max_forbidden_phrase_total),
                "max_forbidden_action_total": int(args.max_forbidden_action_total),
                "max_required_field_missing_total": int(args.max_required_field_missing_total),
                "max_invalid_amount_format_total": int(args.max_invalid_amount_format_total),
                "max_invalid_date_format_total": int(args.max_invalid_date_format_total),
                "max_invalid_status_format_total": int(args.max_invalid_status_format_total),
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
    print(f"output_total={_safe_int(summary.get('output_total'), 0)}")
    print(f"guard_bypass_total={_safe_int(summary.get('guard_bypass_total'), 0)}")
    print(f"forbidden_action_total={_safe_int(summary.get('forbidden_action_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
