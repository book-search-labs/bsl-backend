#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REQUIRED_SOURCE_TYPES = {"OFFICIAL_POLICY", "EVENT_NOTICE", "ANNOUNCEMENT", "USER_GENERATED"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
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
    for key in ("updated_at", "timestamp", "created_at", "event_time", "generated_at"):
        ts = _parse_ts(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_source_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "POLICY": "OFFICIAL_POLICY",
        "EVENT": "EVENT_NOTICE",
        "NOTICE": "ANNOUNCEMENT",
        "UGC": "USER_GENERATED",
    }
    if text in REQUIRED_SOURCE_TYPES:
        return text
    return aliases.get(text, text or "UNKNOWN")


def read_policies(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except Exception:
        payload = None

    if isinstance(payload, list):
        rows.extend(item for item in payload if isinstance(item, dict))
    elif isinstance(payload, dict):
        items = payload.get("items") if isinstance(payload.get("items"), list) else [payload]
        rows.extend(item for item in items if isinstance(item, dict))
    else:
        for line in text.splitlines():
            line_text = line.strip()
            if not line_text:
                continue
            try:
                item = json.loads(line_text)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def summarize_registry(policies: list[Mapping[str, Any]], *, max_policy_age_days: float, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or datetime.now(timezone.utc)
    invalid_weight_total = 0
    invalid_ttl_total = 0
    missing_version_total = 0
    stale_policy_total = 0
    latest_ts: datetime | None = None
    source_rows: dict[str, int] = {}

    for row in policies:
        source_type = _normalize_source_type(row.get("source_type") or row.get("type"))
        trust_weight = _safe_float(row.get("trust_weight"), -1.0)
        freshness_ttl = _safe_float(row.get("freshness_ttl"), _safe_float(row.get("freshness_ttl_sec"), -1.0))
        version = str(row.get("version") or "").strip()
        ts = _event_ts(row)

        source_rows[source_type] = source_rows.get(source_type, 0) + 1

        if trust_weight < 0.0 or trust_weight > 1.0:
            invalid_weight_total += 1
        if freshness_ttl <= 0.0:
            invalid_ttl_total += 1
        if not version:
            missing_version_total += 1

        if ts is not None:
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
            age_days = max(0.0, (now_dt - ts).total_seconds() / 86400.0)
            if age_days > max(0.0, float(max_policy_age_days)):
                stale_policy_total += 1

    policy_total = len(policies)
    covered_types = {key for key in source_rows.keys() if key in REQUIRED_SOURCE_TYPES}
    coverage_ratio = 0.0 if not REQUIRED_SOURCE_TYPES else float(len(covered_types)) / float(len(REQUIRED_SOURCE_TYPES))
    stale_ratio = 0.0 if policy_total == 0 else float(stale_policy_total) / float(policy_total)
    stale_minutes = 0.0
    if latest_ts is not None:
        stale_minutes = max(0.0, (now_dt - latest_ts).total_seconds() / 60.0)

    return {
        "policy_total": policy_total,
        "coverage_ratio": coverage_ratio,
        "missing_source_types": sorted(list(REQUIRED_SOURCE_TYPES - covered_types)),
        "invalid_weight_total": invalid_weight_total,
        "invalid_ttl_total": invalid_ttl_total,
        "missing_version_total": missing_version_total,
        "stale_policy_total": stale_policy_total,
        "stale_ratio": stale_ratio,
        "source_distribution": [{"source_type": key, "count": value} for key, value in sorted(source_rows.items(), key=lambda item: item[0])],
        "latest_policy_time": latest_ts.isoformat() if latest_ts else None,
        "stale_minutes": stale_minutes,
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_policy_total: int,
    min_coverage_ratio: float,
    max_invalid_weight_total: int,
    max_invalid_ttl_total: int,
    max_missing_version_total: int,
    max_stale_ratio: float,
    max_stale_minutes: float,
) -> list[str]:
    failures: list[str] = []
    policy_total = _safe_int(summary.get("policy_total"), 0)
    coverage_ratio = _safe_float(summary.get("coverage_ratio"), 0.0)
    invalid_weight_total = _safe_int(summary.get("invalid_weight_total"), 0)
    invalid_ttl_total = _safe_int(summary.get("invalid_ttl_total"), 0)
    missing_version_total = _safe_int(summary.get("missing_version_total"), 0)
    stale_ratio = _safe_float(summary.get("stale_ratio"), 0.0)
    stale_minutes = _safe_float(summary.get("stale_minutes"), 0.0)

    if policy_total < max(0, int(min_policy_total)):
        failures.append(f"source trust policy total too small: {policy_total} < {int(min_policy_total)}")
    if policy_total == 0:
        return failures

    if coverage_ratio < max(0.0, float(min_coverage_ratio)):
        failures.append(f"source type coverage ratio below threshold: {coverage_ratio:.4f} < {float(min_coverage_ratio):.4f}")
    if invalid_weight_total > max(0, int(max_invalid_weight_total)):
        failures.append(f"invalid trust weight total exceeded: {invalid_weight_total} > {int(max_invalid_weight_total)}")
    if invalid_ttl_total > max(0, int(max_invalid_ttl_total)):
        failures.append(f"invalid freshness ttl total exceeded: {invalid_ttl_total} > {int(max_invalid_ttl_total)}")
    if missing_version_total > max(0, int(max_missing_version_total)):
        failures.append(f"missing policy version total exceeded: {missing_version_total} > {int(max_missing_version_total)}")
    if stale_ratio > max(0.0, float(max_stale_ratio)):
        failures.append(f"stale policy ratio exceeded: {stale_ratio:.4f} > {float(max_stale_ratio):.4f}")
    if stale_minutes > max(0.0, float(max_stale_minutes)):
        failures.append(f"source trust policy events stale: {stale_minutes:.1f}m > {float(max_stale_minutes):.1f}m")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Source Trust Registry")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- policy_json: {payload.get('policy_json')}")
    lines.append(f"- policy_total: {_safe_int(summary.get('policy_total'), 0)}")
    lines.append(f"- coverage_ratio: {_safe_float(summary.get('coverage_ratio'), 0.0):.4f}")
    lines.append(f"- invalid_weight_total: {_safe_int(summary.get('invalid_weight_total'), 0)}")
    lines.append(f"- invalid_ttl_total: {_safe_int(summary.get('invalid_ttl_total'), 0)}")
    lines.append(f"- stale_ratio: {_safe_float(summary.get('stale_ratio'), 0.0):.4f}")
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
    parser = argparse.ArgumentParser(description="Evaluate source trust registry completeness and freshness.")
    parser.add_argument("--policy-json", default="var/chat_trust/source_trust_policy.json")
    parser.add_argument("--max-policy-age-days", type=float, default=7.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_source_trust_registry")
    parser.add_argument("--min-policy-total", type=int, default=1)
    parser.add_argument("--min-coverage-ratio", type=float, default=1.0)
    parser.add_argument("--max-invalid-weight-total", type=int, default=0)
    parser.add_argument("--max-invalid-ttl-total", type=int, default=0)
    parser.add_argument("--max-missing-version-total", type=int, default=0)
    parser.add_argument("--max-stale-ratio", type=float, default=0.10)
    parser.add_argument("--max-stale-minutes", type=float, default=60.0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    policy_path = Path(args.policy_json)
    policies = read_policies(policy_path)
    summary = summarize_registry(
        policies,
        max_policy_age_days=max(0.0, float(args.max_policy_age_days)),
    )
    failures = evaluate_gate(
        summary,
        min_policy_total=max(0, int(args.min_policy_total)),
        min_coverage_ratio=max(0.0, float(args.min_coverage_ratio)),
        max_invalid_weight_total=max(0, int(args.max_invalid_weight_total)),
        max_invalid_ttl_total=max(0, int(args.max_invalid_ttl_total)),
        max_missing_version_total=max(0, int(args.max_missing_version_total)),
        max_stale_ratio=max(0.0, float(args.max_stale_ratio)),
        max_stale_minutes=max(0.0, float(args.max_stale_minutes)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_json": str(policy_path),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_policy_total": int(args.min_policy_total),
                "min_coverage_ratio": float(args.min_coverage_ratio),
                "max_invalid_weight_total": int(args.max_invalid_weight_total),
                "max_invalid_ttl_total": int(args.max_invalid_ttl_total),
                "max_missing_version_total": int(args.max_missing_version_total),
                "max_stale_ratio": float(args.max_stale_ratio),
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
    print(f"policy_total={_safe_int(summary.get('policy_total'), 0)}")
    print(f"coverage_ratio={_safe_float(summary.get('coverage_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
