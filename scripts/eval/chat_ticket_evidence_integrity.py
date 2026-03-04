#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


def _pack_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    pack = row.get("evidence_pack")
    if isinstance(pack, Mapping):
        return {str(k): v for k, v in pack.items()}
    return {str(k): v for k, v in row.items()}


def _extract_links(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = pack.get("evidence_links")
    if raw is None:
        raw = pack.get("sources")
    if raw is None:
        raw = pack.get("citations")

    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, Mapping):
        items = [raw]
    elif isinstance(raw, str) and raw.strip():
        items = [raw.strip()]
    else:
        items = []

    links: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            links.append(
                {
                    "url": str(item.get("url") or item.get("link") or item.get("source") or "").strip(),
                    "status": str(item.get("status") or item.get("state") or "").strip().upper(),
                    "reachable": item.get("reachable"),
                }
            )
        else:
            links.append({"url": str(item or "").strip(), "status": "", "reachable": None})
    return links


def _is_valid_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _has_tool_version(pack: Mapping[str, Any]) -> bool:
    top = str(pack.get("tool_version") or pack.get("tools_version") or "").strip()
    if top:
        return True
    tools = pack.get("executed_tools")
    if tools is None:
        tools = pack.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, Mapping):
                version = str(tool.get("version") or tool.get("tool_version") or "").strip()
                if version:
                    return True
    return False


def summarize_evidence_integrity(rows: list[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    latest_ts: datetime | None = None

    pack_total = 0
    missing_link_total = 0
    invalid_url_total = 0
    unresolved_link_total = 0
    missing_policy_version_total = 0
    missing_tool_version_total = 0
    missing_evidence_hash_total = 0

    for row in rows:
        pack = _pack_payload(row)
        pack_total += 1

        ts = _event_ts(pack) or _event_ts(row)
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        links = _extract_links(pack)
        if len(links) == 0:
            missing_link_total += 1

        for link in links:
            url = str(link.get("url") or "").strip()
            status = str(link.get("status") or "").strip().upper()
            reachable = link.get("reachable")
            if not _is_valid_url(url):
                invalid_url_total += 1
            if status in {"BROKEN", "NOT_FOUND", "ERROR", "UNREACHABLE"} or reachable is False:
                unresolved_link_total += 1

        policy_version = str(pack.get("policy_version") or row.get("policy_version") or "").strip()
        if not policy_version:
            missing_policy_version_total += 1

        if not _has_tool_version(pack):
            missing_tool_version_total += 1

        evidence_hash = str(pack.get("evidence_hash") or pack.get("pack_hash") or row.get("evidence_hash") or "").strip()
        if not evidence_hash:
            missing_evidence_hash_total += 1

    stale_minutes = 999999.0 if latest_ts is None else max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "window_size": len(rows),
        "pack_total": pack_total,
        "missing_link_total": missing_link_total,
        "invalid_url_total": invalid_url_total,
        "unresolved_link_total": unresolved_link_total,
        "missing_policy_version_total": missing_policy_version_total,
        "missing_tool_version_total": missing_tool_version_total,
        "missing_evidence_hash_total": missing_evidence_hash_total,
        "latest_event_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_window: int,
    max_missing_link_total: int,
    max_invalid_url_total: int,
    max_unresolved_link_total: int,
    max_missing_policy_version_total: int,
    max_missing_tool_version_total: int,
    max_missing_evidence_hash_total: int,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    window_size = _safe_int(summary.get("window_size"), 0)
    missing_link_total = _safe_int(summary.get("missing_link_total"), 0)
    invalid_url_total = _safe_int(summary.get("invalid_url_total"), 0)
    unresolved_link_total = _safe_int(summary.get("unresolved_link_total"), 0)
    missing_policy_version_total = _safe_int(summary.get("missing_policy_version_total"), 0)
    missing_tool_version_total = _safe_int(summary.get("missing_tool_version_total"), 0)
    missing_evidence_hash_total = _safe_int(summary.get("missing_evidence_hash_total"), 0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 999999.0)

    if window_size < max(0, int(min_window)):
        failures.append(f"ticket evidence integrity window too small: {window_size} < {int(min_window)}")
    if window_size == 0:
        return failures

    if missing_link_total > max(0, int(max_missing_link_total)):
        failures.append(f"ticket evidence missing link total exceeded: {missing_link_total} > {int(max_missing_link_total)}")
    if invalid_url_total > max(0, int(max_invalid_url_total)):
        failures.append(f"ticket evidence invalid URL total exceeded: {invalid_url_total} > {int(max_invalid_url_total)}")
    if unresolved_link_total > max(0, int(max_unresolved_link_total)):
        failures.append(f"ticket evidence unresolved link total exceeded: {unresolved_link_total} > {int(max_unresolved_link_total)}")
    if missing_policy_version_total > max(0, int(max_missing_policy_version_total)):
        failures.append(
            "ticket evidence missing policy version total exceeded: "
            f"{missing_policy_version_total} > {int(max_missing_policy_version_total)}"
        )
    if missing_tool_version_total > max(0, int(max_missing_tool_version_total)):
        failures.append(
            f"ticket evidence missing tool version total exceeded: {missing_tool_version_total} > {int(max_missing_tool_version_total)}"
        )
    if missing_evidence_hash_total > max(0, int(max_missing_evidence_hash_total)):
        failures.append(
            f"ticket evidence missing hash total exceeded: {missing_evidence_hash_total} > {int(max_missing_evidence_hash_total)}"
        )
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"ticket evidence integrity stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_pack_total_drop: int,
    max_missing_link_total_increase: int,
    max_invalid_url_total_increase: int,
    max_unresolved_link_total_increase: int,
    max_missing_policy_version_total_increase: int,
    max_missing_tool_version_total_increase: int,
    max_missing_evidence_hash_total_increase: int,
    max_stale_minutes_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_pack_total = _safe_int(base_summary.get("pack_total"), 0)
    cur_pack_total = _safe_int(current_summary.get("pack_total"), 0)
    pack_total_drop = max(0, base_pack_total - cur_pack_total)
    if pack_total_drop > max(0, int(max_pack_total_drop)):
        failures.append(
            "pack_total regression: "
            f"baseline={base_pack_total}, current={cur_pack_total}, "
            f"allowed_drop={max(0, int(max_pack_total_drop))}"
        )

    baseline_increase_pairs = [
        ("missing_link_total", max_missing_link_total_increase),
        ("invalid_url_total", max_invalid_url_total_increase),
        ("unresolved_link_total", max_unresolved_link_total_increase),
        ("missing_policy_version_total", max_missing_policy_version_total_increase),
        ("missing_tool_version_total", max_missing_tool_version_total_increase),
        ("missing_evidence_hash_total", max_missing_evidence_hash_total_increase),
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
    lines.append("# Chat Ticket Evidence Integrity")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- packs_jsonl: {payload.get('packs_jsonl')}")
    lines.append(f"- pack_total: {_safe_int(summary.get('pack_total'), 0)}")
    lines.append(f"- missing_link_total: {_safe_int(summary.get('missing_link_total'), 0)}")
    lines.append(f"- invalid_url_total: {_safe_int(summary.get('invalid_url_total'), 0)}")
    lines.append(f"- unresolved_link_total: {_safe_int(summary.get('unresolved_link_total'), 0)}")
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
    else:
        if not failures:
            lines.append("- failure: (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat ticket evidence integrity quality.")
    parser.add_argument("--packs-jsonl", default="var/chat_ticket/evidence_packs.jsonl")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_ticket_evidence_integrity")
    parser.add_argument("--min-window", type=int, default=0)
    parser.add_argument("--max-missing-link-total", type=int, default=0)
    parser.add_argument("--max-invalid-url-total", type=int, default=0)
    parser.add_argument("--max-unresolved-link-total", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total", type=int, default=0)
    parser.add_argument("--max-missing-tool-version-total", type=int, default=0)
    parser.add_argument("--max-missing-evidence-hash-total", type=int, default=0)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-pack-total-drop", type=int, default=10)
    parser.add_argument("--max-missing-link-total-increase", type=int, default=0)
    parser.add_argument("--max-invalid-url-total-increase", type=int, default=0)
    parser.add_argument("--max-unresolved-link-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-policy-version-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-tool-version-total-increase", type=int, default=0)
    parser.add_argument("--max-missing-evidence-hash-total-increase", type=int, default=0)
    parser.add_argument("--max-stale-minutes-increase", type=float, default=30.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _read_jsonl(
        Path(args.packs_jsonl),
        window_hours=max(1, int(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    summary = summarize_evidence_integrity(rows)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_missing_link_total=max(0, int(args.max_missing_link_total)),
        max_invalid_url_total=max(0, int(args.max_invalid_url_total)),
        max_unresolved_link_total=max(0, int(args.max_unresolved_link_total)),
        max_missing_policy_version_total=max(0, int(args.max_missing_policy_version_total)),
        max_missing_tool_version_total=max(0, int(args.max_missing_tool_version_total)),
        max_missing_evidence_hash_total=max(0, int(args.max_missing_evidence_hash_total)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_pack_total_drop=max(0, int(args.max_pack_total_drop)),
            max_missing_link_total_increase=max(0, int(args.max_missing_link_total_increase)),
            max_invalid_url_total_increase=max(0, int(args.max_invalid_url_total_increase)),
            max_unresolved_link_total_increase=max(0, int(args.max_unresolved_link_total_increase)),
            max_missing_policy_version_total_increase=max(0, int(args.max_missing_policy_version_total_increase)),
            max_missing_tool_version_total_increase=max(0, int(args.max_missing_tool_version_total_increase)),
            max_missing_evidence_hash_total_increase=max(0, int(args.max_missing_evidence_hash_total_increase)),
            max_stale_minutes_increase=max(0.0, float(args.max_stale_minutes_increase)),
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packs_jsonl": str(args.packs_jsonl),
        "source": {
            "packs_jsonl": str(args.packs_jsonl),
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
                "max_missing_link_total": int(args.max_missing_link_total),
                "max_invalid_url_total": int(args.max_invalid_url_total),
                "max_unresolved_link_total": int(args.max_unresolved_link_total),
                "max_missing_policy_version_total": int(args.max_missing_policy_version_total),
                "max_missing_tool_version_total": int(args.max_missing_tool_version_total),
                "max_missing_evidence_hash_total": int(args.max_missing_evidence_hash_total),
                "max_stale_minutes": float(args.max_stale_minutes),
                "max_pack_total_drop": int(args.max_pack_total_drop),
                "max_missing_link_total_increase": int(args.max_missing_link_total_increase),
                "max_invalid_url_total_increase": int(args.max_invalid_url_total_increase),
                "max_unresolved_link_total_increase": int(args.max_unresolved_link_total_increase),
                "max_missing_policy_version_total_increase": int(args.max_missing_policy_version_total_increase),
                "max_missing_tool_version_total_increase": int(args.max_missing_tool_version_total_increase),
                "max_missing_evidence_hash_total_increase": int(args.max_missing_evidence_hash_total_increase),
                "max_stale_minutes_increase": float(args.max_stale_minutes_increase),
            },
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"pack_total={_safe_int(summary.get('pack_total'), 0)}")
    print(f"invalid_url_total={_safe_int(summary.get('invalid_url_total'), 0)}")
    print(f"unresolved_link_total={_safe_int(summary.get('unresolved_link_total'), 0)}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
