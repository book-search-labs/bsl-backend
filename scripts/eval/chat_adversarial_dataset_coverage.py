#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REQUIRED_ATTACK_TYPES_DEFAULT = {
    "PROMPT_INJECTION",
    "ROLE_CONFUSION",
    "FAKE_POLICY",
    "EMOTIONAL_PRESSURE",
}
COMMERCE_TAGS = {"commerce", "order", "refund", "shipping", "payment", "delivery"}
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")


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


def _as_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if "," in text:
        return [item.strip().lower() for item in text.split(",") if item.strip()]
    return [text.lower()]


def _normalize_attack_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "INJECTION": "PROMPT_INJECTION",
        "PROMPT_INJECT": "PROMPT_INJECTION",
        "ROLE_CONFLICT": "ROLE_CONFUSION",
        "POLICY_SPOOF": "FAKE_POLICY",
        "EMOTIONAL_COERCION": "EMOTIONAL_PRESSURE",
    }
    return aliases.get(text, text)


def _is_korean_case(row: Mapping[str, Any]) -> bool:
    lang = str(row.get("language") or row.get("locale") or "").strip().lower()
    query = str(row.get("query") or row.get("prompt") or "").strip()
    if lang.startswith("ko"):
        return True
    return bool(HANGUL_RE.search(query))


def _is_cjk_mixed_case(row: Mapping[str, Any]) -> bool:
    query = str(row.get("query") or row.get("prompt") or "").strip()
    return bool(HANGUL_RE.search(query) and CJK_RE.search(query))


def _is_commerce_case(row: Mapping[str, Any]) -> bool:
    tags = set(_as_tags(row.get("tags") or row.get("domain_tags")))
    intent = str(row.get("intent") or "").strip().lower()
    if tags.intersection(COMMERCE_TAGS):
        return True
    return intent in {"order_status", "refund_request", "cancel_order", "delivery_tracking", "payment_change"}


def read_cases(path: Path, *, limit: int = 200000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if isinstance(payload, list):
        rows: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, Mapping):
                rows.append({str(k): v for k, v in item.items()})
        return rows[-limit:] if limit > 0 else rows

    rows = []
    for line in text.splitlines():
        row_text = line.strip()
        if not row_text:
            continue
        try:
            row = json.loads(row_text)
        except Exception:
            continue
        if isinstance(row, Mapping):
            rows.append({str(k): v for k, v in row.items()})
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def summarize_dataset_coverage(
    cases: list[Mapping[str, Any]],
    *,
    required_attack_types: set[str],
) -> dict[str, Any]:
    case_total = 0
    invalid_case_total = 0
    korean_case_total = 0
    cjk_mixed_total = 0
    commerce_case_total = 0
    attack_types: dict[str, int] = {}

    for row in cases:
        case_total += 1
        case_id = str(row.get("case_id") or row.get("id") or "").strip()
        query = str(row.get("query") or row.get("prompt") or "").strip()
        attack_type = _normalize_attack_type(row.get("attack_type") or row.get("category"))
        if not case_id or not query or not attack_type:
            invalid_case_total += 1
            continue

        attack_types[attack_type] = attack_types.get(attack_type, 0) + 1
        if _is_korean_case(row):
            korean_case_total += 1
        if _is_cjk_mixed_case(row):
            cjk_mixed_total += 1
        if _is_commerce_case(row):
            commerce_case_total += 1

    korean_case_ratio = 0.0 if case_total == 0 else float(korean_case_total) / float(case_total)
    missing_attack_types = sorted([attack for attack in required_attack_types if attack not in attack_types])

    return {
        "case_total": case_total,
        "invalid_case_total": invalid_case_total,
        "korean_case_total": korean_case_total,
        "korean_case_ratio": korean_case_ratio,
        "cjk_mixed_total": cjk_mixed_total,
        "commerce_case_total": commerce_case_total,
        "attack_type_total": len(attack_types),
        "missing_attack_types": missing_attack_types,
        "attack_type_distribution": [
            {"attack_type": key, "count": value}
            for key, value in sorted(attack_types.items(), key=lambda item: item[0])
        ],
    }


def evaluate_gate(
    summary: Mapping[str, Any],
    *,
    min_case_total: int,
    max_missing_attack_type_total: int,
    min_korean_case_ratio: float,
    min_cjk_mixed_total: int,
    min_commerce_case_total: int,
    max_invalid_case_total: int,
) -> list[str]:
    failures: list[str] = []
    case_total = _safe_int(summary.get("case_total"), 0)
    missing_attack_type_total = len(summary.get("missing_attack_types") if isinstance(summary.get("missing_attack_types"), list) else [])
    korean_case_ratio = _safe_float(summary.get("korean_case_ratio"), 0.0)
    cjk_mixed_total = _safe_int(summary.get("cjk_mixed_total"), 0)
    commerce_case_total = _safe_int(summary.get("commerce_case_total"), 0)
    invalid_case_total = _safe_int(summary.get("invalid_case_total"), 0)

    if case_total < max(0, int(min_case_total)):
        failures.append(f"adversarial dataset too small: {case_total} < {int(min_case_total)}")
    if case_total == 0:
        return failures

    if missing_attack_type_total > max(0, int(max_missing_attack_type_total)):
        failures.append(
            f"adversarial dataset missing attack type total exceeded: {missing_attack_type_total} > {int(max_missing_attack_type_total)}"
        )
    if korean_case_ratio < max(0.0, float(min_korean_case_ratio)):
        failures.append(f"adversarial korean case ratio below threshold: {korean_case_ratio:.4f} < {float(min_korean_case_ratio):.4f}")
    if cjk_mixed_total < max(0, int(min_cjk_mixed_total)):
        failures.append(f"adversarial cjk mixed case total too small: {cjk_mixed_total} < {int(min_cjk_mixed_total)}")
    if commerce_case_total < max(0, int(min_commerce_case_total)):
        failures.append(f"adversarial commerce case total too small: {commerce_case_total} < {int(min_commerce_case_total)}")
    if invalid_case_total > max(0, int(max_invalid_case_total)):
        failures.append(f"adversarial invalid case total exceeded: {invalid_case_total} > {int(max_invalid_case_total)}")
    return failures


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Chat Adversarial Dataset Coverage")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- dataset_jsonl: {payload.get('dataset_jsonl')}")
    lines.append(f"- case_total: {_safe_int(summary.get('case_total'), 0)}")
    lines.append(f"- korean_case_ratio: {_safe_float(summary.get('korean_case_ratio'), 0.0):.4f}")
    lines.append(f"- cjk_mixed_total: {_safe_int(summary.get('cjk_mixed_total'), 0)}")
    lines.append(f"- commerce_case_total: {_safe_int(summary.get('commerce_case_total'), 0)}")
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
    parser = argparse.ArgumentParser(description="Evaluate adversarial dataset coverage for Korean safety regression.")
    parser.add_argument("--dataset-jsonl", default="evaluation/chat_safety/adversarial_cases.jsonl")
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument(
        "--required-attack-types",
        default="PROMPT_INJECTION,ROLE_CONFUSION,FAKE_POLICY,EMOTIONAL_PRESSURE",
    )
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_adversarial_dataset_coverage")
    parser.add_argument("--min-case-total", type=int, default=0)
    parser.add_argument("--max-missing-attack-type-total", type=int, default=0)
    parser.add_argument("--min-korean-case-ratio", type=float, default=0.4)
    parser.add_argument("--min-cjk-mixed-total", type=int, default=0)
    parser.add_argument("--min-commerce-case-total", type=int, default=0)
    parser.add_argument("--max-invalid-case-total", type=int, default=0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset_jsonl)
    cases = read_cases(dataset_path, limit=max(1, int(args.limit)))
    required_attack_types = {
        item.strip().upper() for item in str(args.required_attack_types).split(",") if item.strip()
    } or set(REQUIRED_ATTACK_TYPES_DEFAULT)
    summary = summarize_dataset_coverage(cases, required_attack_types=required_attack_types)
    failures = evaluate_gate(
        summary,
        min_case_total=max(0, int(args.min_case_total)),
        max_missing_attack_type_total=max(0, int(args.max_missing_attack_type_total)),
        min_korean_case_ratio=max(0.0, float(args.min_korean_case_ratio)),
        min_cjk_mixed_total=max(0, int(args.min_cjk_mixed_total)),
        min_commerce_case_total=max(0, int(args.min_commerce_case_total)),
        max_invalid_case_total=max(0, int(args.max_invalid_case_total)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_jsonl": str(dataset_path),
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_case_total": int(args.min_case_total),
                "max_missing_attack_type_total": int(args.max_missing_attack_type_total),
                "min_korean_case_ratio": float(args.min_korean_case_ratio),
                "min_cjk_mixed_total": int(args.min_cjk_mixed_total),
                "min_commerce_case_total": int(args.min_commerce_case_total),
                "max_invalid_case_total": int(args.max_invalid_case_total),
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
    print(f"case_total={_safe_int(summary.get('case_total'), 0)}")
    print(f"korean_case_ratio={_safe_float(summary.get('korean_case_ratio'), 0.0):.4f}")

    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
