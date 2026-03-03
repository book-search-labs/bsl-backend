#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


FAIL_RESULTS = {"FAIL", "INVALID_SIGNATURE", "INVALID_CHECKSUM", "UNTRUSTED_SIGNER", "MISSING_SIGNATURE"}


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


def _artifact_event(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("artifact_id") or row.get("bundle_id") or row.get("prompt_bundle_id") or "").strip())


def _signature_present(row: Mapping[str, Any]) -> bool:
    if "signature_present" in row:
        return _safe_bool(row.get("signature_present"), False)
    return bool(str(row.get("signature") or row.get("artifact_signature") or "").strip())


def _signer_trusted(row: Mapping[str, Any]) -> bool:
    if "signer_trusted" in row:
        return _safe_bool(row.get("signer_trusted"), False)
    trust = str(row.get("signer_trust") or "").strip().lower()
    if trust:
        return trust in {"trusted", "verified"}
    return True


def _checksum_match(row: Mapping[str, Any]) -> bool:
    if "checksum_match" in row:
        return _safe_bool(row.get("checksum_match"), True)
    expected = str(row.get("expected_checksum") or "").strip()
    actual = str(row.get("actual_checksum") or "").strip()
    if expected and actual:
        return expected == actual
    return True


def _verify_failed(row: Mapping[str, Any]) -> bool:
    if _safe_bool(row.get("signature_verify_failed"), False):
        return True
    verify_result = str(row.get("verify_result") or row.get("verification_result") or "").strip().upper()
    if verify_result:
        return verify_result in FAIL_RESULTS
    if not _signature_present(row):
        return True
    if not _signer_trusted(row):
        return True
    return not _checksum_match(row)


def _deploy_allowed(row: Mapping[str, Any]) -> bool:
    if "deploy_allowed" in row:
        return _safe_bool(row.get("deploy_allowed"), True)
    decision = str(row.get("deployment_decision") or row.get("load_decision") or "").strip().upper()
    if decision:
        return decision in {"ALLOW", "PROCEED", "LOAD"}
    return True


def _reason_present(row: Mapping[str, Any]) -> bool:
    return bool(str(row.get("reason_code") or row.get("verify_reason_code") or "").strip())


def summarize_prompt_signature_verification_guard(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    artifact_total = 0
    signature_verified_total = 0
    signature_verify_fail_total = 0
    unsigned_artifact_total = 0
    untrusted_signer_total = 0
    checksum_mismatch_total = 0
    deploy_block_total = 0
    unblocked_tampered_total = 0
    reason_code_missing_total = 0

    for row in rows:
        ts = _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        if not _artifact_event(row):
            continue
        artifact_total += 1

        signature_present = _signature_present(row)
        signer_trusted = _signer_trusted(row)
        checksum_match = _checksum_match(row)
        verify_failed = _verify_failed(row)
        deploy_allowed = _deploy_allowed(row)
        reason_present = _reason_present(row)

        if not signature_present:
            unsigned_artifact_total += 1
        if not signer_trusted:
            untrusted_signer_total += 1
        if not checksum_match:
            checksum_mismatch_total += 1

        if verify_failed:
            signature_verify_fail_total += 1
            if deploy_allowed:
                unblocked_tampered_total += 1
            else:
                deploy_block_total += 1
        else:
            signature_verified_total += 1

        if verify_failed and not reason_present:
            reason_code_missing_total += 1

    signature_verified_ratio = 1.0 if artifact_total == 0 else float(signature_verified_total) / float(artifact_total)
    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "artifact_total": artifact_total,
        "signature_verified_total": signature_verified_total,
        "signature_verified_ratio": signature_verified_ratio,
        "signature_verify_fail_total": signature_verify_fail_total,
        "unsigned_artifact_total": unsigned_artifact_total,
        "untrusted_signer_total": untrusted_signer_total,
        "checksum_mismatch_total": checksum_mismatch_total,
        "deploy_block_total": deploy_block_total,
        "unblocked_tampered_total": unblocked_tampered_total,
        "reason_code_missing_total": reason_code_missing_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    min_artifact_total: int,
    min_signature_verified_ratio: float,
    max_signature_verify_fail_total: int,
    max_unsigned_artifact_total: int,
    max_untrusted_signer_total: int,
    max_checksum_mismatch_total: int,
    max_unblocked_tampered_total: int,
    max_reason_code_missing_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    artifact_total = _safe_int(summary.get("artifact_total"), 0)
    signature_verified_ratio = _safe_float(summary.get("signature_verified_ratio"), 0.0)
    signature_verify_fail_total = _safe_int(summary.get("signature_verify_fail_total"), 0)
    unsigned_artifact_total = _safe_int(summary.get("unsigned_artifact_total"), 0)
    untrusted_signer_total = _safe_int(summary.get("untrusted_signer_total"), 0)
    checksum_mismatch_total = _safe_int(summary.get("checksum_mismatch_total"), 0)
    unblocked_tampered_total = _safe_int(summary.get("unblocked_tampered_total"), 0)
    reason_code_missing_total = _safe_int(summary.get("reason_code_missing_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"chat prompt signature window too small: {window_size} < {int(min_window)}")
    if artifact_total < max(0, int(min_artifact_total)):
        failures.append(f"chat prompt signature artifact total too small: {artifact_total} < {int(min_artifact_total)}")
    if window_size == 0:
        return failures

    if signature_verified_ratio < max(0.0, float(min_signature_verified_ratio)):
        failures.append(
            f"chat prompt signature verified ratio below minimum: {signature_verified_ratio:.4f} < {float(min_signature_verified_ratio):.4f}"
        )
    if signature_verify_fail_total > max(0, int(max_signature_verify_fail_total)):
        failures.append(
            f"chat prompt signature verify fail total exceeded: {signature_verify_fail_total} > {int(max_signature_verify_fail_total)}"
        )
    if unsigned_artifact_total > max(0, int(max_unsigned_artifact_total)):
        failures.append(
            f"chat prompt signature unsigned artifact total exceeded: {unsigned_artifact_total} > {int(max_unsigned_artifact_total)}"
        )
    if untrusted_signer_total > max(0, int(max_untrusted_signer_total)):
        failures.append(
            f"chat prompt signature untrusted signer total exceeded: {untrusted_signer_total} > {int(max_untrusted_signer_total)}"
        )
    if checksum_mismatch_total > max(0, int(max_checksum_mismatch_total)):
        failures.append(
            f"chat prompt signature checksum mismatch total exceeded: {checksum_mismatch_total} > {int(max_checksum_mismatch_total)}"
        )
    if unblocked_tampered_total > max(0, int(max_unblocked_tampered_total)):
        failures.append(
            "chat prompt signature unblocked tampered total exceeded: "
            f"{unblocked_tampered_total} > {int(max_unblocked_tampered_total)}"
        )
    if reason_code_missing_total > max(0, int(max_reason_code_missing_total)):
        failures.append(
            f"chat prompt signature reason code missing total exceeded: {reason_code_missing_total} > {int(max_reason_code_missing_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"chat prompt signature stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Prompt Signature Verification Guard")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- events_jsonl: {payload.get('events_jsonl')}")
    lines.append(f"- artifact_total: {_safe_int(summary.get('artifact_total'), 0)}")
    lines.append(f"- signature_verified_ratio: {_safe_float(summary.get('signature_verified_ratio'), 0.0):.4f}")
    lines.append(f"- signature_verify_fail_total: {_safe_int(summary.get('signature_verify_fail_total'), 0)}")
    lines.append(f"- unblocked_tampered_total: {_safe_int(summary.get('unblocked_tampered_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate prompt signature verification integrity.")
    parser.add_argument("--events-jsonl", default="var/chat_prompt_supply/signature_events.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_prompt_signature_verification_guard")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--min-artifact-total", type=int, default=0)
    parser.add_argument("--min-signature-verified-ratio", type=float, default=0.0)
    parser.add_argument("--max-signature-verify-fail-total", type=int, default=1000000)
    parser.add_argument("--max-unsigned-artifact-total", type=int, default=1000000)
    parser.add_argument("--max-untrusted-signer-total", type=int, default=1000000)
    parser.add_argument("--max-checksum-mismatch-total", type=int, default=1000000)
    parser.add_argument("--max-unblocked-tampered-total", type=int, default=1000000)
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
    summary = summarize_prompt_signature_verification_guard(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        min_artifact_total=max(0, int(args.min_artifact_total)),
        min_signature_verified_ratio=max(0.0, float(args.min_signature_verified_ratio)),
        max_signature_verify_fail_total=max(0, int(args.max_signature_verify_fail_total)),
        max_unsigned_artifact_total=max(0, int(args.max_unsigned_artifact_total)),
        max_untrusted_signer_total=max(0, int(args.max_untrusted_signer_total)),
        max_checksum_mismatch_total=max(0, int(args.max_checksum_mismatch_total)),
        max_unblocked_tampered_total=max(0, int(args.max_unblocked_tampered_total)),
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
                "min_window": int(args.min_window),
                "min_artifact_total": int(args.min_artifact_total),
                "min_signature_verified_ratio": float(args.min_signature_verified_ratio),
                "max_signature_verify_fail_total": int(args.max_signature_verify_fail_total),
                "max_unsigned_artifact_total": int(args.max_unsigned_artifact_total),
                "max_untrusted_signer_total": int(args.max_untrusted_signer_total),
                "max_checksum_mismatch_total": int(args.max_checksum_mismatch_total),
                "max_unblocked_tampered_total": int(args.max_unblocked_tampered_total),
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
    print(f"artifact_total={_safe_int(summary.get('artifact_total'), 0)}")
    print(f"signature_verified_ratio={_safe_float(summary.get('signature_verified_ratio'), 0.0):.4f}")
    print(f"unblocked_tampered_total={_safe_int(summary.get('unblocked_tampered_total'), 0)}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
