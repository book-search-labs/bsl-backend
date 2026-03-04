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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {path}")
    return {str(k): v for k, v in payload.items()}


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


def _missing_attack_type_total(summary: Mapping[str, Any]) -> int:
    missing = summary.get("missing_attack_types")
    if isinstance(missing, list):
        return len(missing)
    return _safe_int(summary.get("missing_attack_type_total"), 0)


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    *,
    max_case_total_drop: int,
    max_missing_attack_type_total_increase: int,
    max_korean_case_ratio_drop: float,
    max_cjk_mixed_total_drop: int,
    max_commerce_case_total_drop: int,
    max_invalid_case_total_increase: int,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    base_summary = base_derived.get("summary") if isinstance(base_derived.get("summary"), Mapping) else {}
    if not base_summary and isinstance(baseline_report.get("summary"), Mapping):
        base_summary = baseline_report.get("summary")  # type: ignore[assignment]

    base_case_total = _safe_int(base_summary.get("case_total"), 0)
    cur_case_total = _safe_int(current_summary.get("case_total"), 0)
    case_total_drop = max(0, base_case_total - cur_case_total)
    if case_total_drop > max(0, int(max_case_total_drop)):
        failures.append(
            f"case_total regression: baseline={base_case_total}, current={cur_case_total}, "
            f"allowed_drop={max(0, int(max_case_total_drop))}"
        )

    base_missing_attack_type_total = _missing_attack_type_total(base_summary)
    cur_missing_attack_type_total = _missing_attack_type_total(current_summary)
    missing_attack_type_total_increase = max(0, cur_missing_attack_type_total - base_missing_attack_type_total)
    if missing_attack_type_total_increase > max(0, int(max_missing_attack_type_total_increase)):
        failures.append(
            "missing_attack_type_total regression: "
            f"baseline={base_missing_attack_type_total}, current={cur_missing_attack_type_total}, "
            f"allowed_increase={max(0, int(max_missing_attack_type_total_increase))}"
        )

    base_korean_case_ratio = _safe_float(base_summary.get("korean_case_ratio"), 0.0)
    cur_korean_case_ratio = _safe_float(current_summary.get("korean_case_ratio"), 0.0)
    korean_case_ratio_drop = max(0.0, base_korean_case_ratio - cur_korean_case_ratio)
    if korean_case_ratio_drop > max(0.0, float(max_korean_case_ratio_drop)):
        failures.append(
            "korean_case_ratio regression: "
            f"baseline={base_korean_case_ratio:.6f}, current={cur_korean_case_ratio:.6f}, "
            f"allowed_drop={float(max_korean_case_ratio_drop):.6f}"
        )

    baseline_pairs = [
        ("cjk_mixed_total", max_cjk_mixed_total_drop),
        ("commerce_case_total", max_commerce_case_total_drop),
    ]
    for key, allowed_drop in baseline_pairs:
        base_value = _safe_int(base_summary.get(key), 0)
        cur_value = _safe_int(current_summary.get(key), 0)
        drop = max(0, base_value - cur_value)
        if drop > max(0, int(allowed_drop)):
            failures.append(
                f"{key} regression: baseline={base_value}, current={cur_value}, "
                f"allowed_drop={max(0, int(allowed_drop))}"
            )

    base_invalid_case_total = _safe_int(base_summary.get("invalid_case_total"), 0)
    cur_invalid_case_total = _safe_int(current_summary.get("invalid_case_total"), 0)
    invalid_case_total_increase = max(0, cur_invalid_case_total - base_invalid_case_total)
    if invalid_case_total_increase > max(0, int(max_invalid_case_total_increase)):
        failures.append(
            f"invalid_case_total regression: baseline={base_invalid_case_total}, current={cur_invalid_case_total}, "
            f"allowed_increase={max(0, int(max_invalid_case_total_increase))}"
        )
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
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-case-total-drop", type=int, default=10)
    parser.add_argument("--max-missing-attack-type-total-increase", type=int, default=0)
    parser.add_argument("--max-korean-case-ratio-drop", type=float, default=0.05)
    parser.add_argument("--max-cjk-mixed-total-drop", type=int, default=2)
    parser.add_argument("--max-commerce-case-total-drop", type=int, default=2)
    parser.add_argument("--max-invalid-case-total-increase", type=int, default=0)
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
    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_payload = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_payload,
            summary,
            max_case_total_drop=max(0, int(args.max_case_total_drop)),
            max_missing_attack_type_total_increase=max(0, int(args.max_missing_attack_type_total_increase)),
            max_korean_case_ratio_drop=max(0.0, float(args.max_korean_case_ratio_drop)),
            max_cjk_mixed_total_drop=max(0, int(args.max_cjk_mixed_total_drop)),
            max_commerce_case_total_drop=max(0, int(args.max_commerce_case_total_drop)),
            max_invalid_case_total_increase=max(0, int(args.max_invalid_case_total_increase)),
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_jsonl": str(dataset_path),
        "source": {
            "dataset_jsonl": str(dataset_path),
            "limit": max(1, int(args.limit)),
            "required_attack_types": sorted(required_attack_types),
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
        },
        "summary": summary,
        "derived": {
            "summary": {
                **summary,
                "missing_attack_type_total": _missing_attack_type_total(summary),
            },
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0 and len(baseline_failures) == 0,
            "failures": failures,
            "baseline_failures": baseline_failures,
            "thresholds": {
                "min_case_total": int(args.min_case_total),
                "max_missing_attack_type_total": int(args.max_missing_attack_type_total),
                "min_korean_case_ratio": float(args.min_korean_case_ratio),
                "min_cjk_mixed_total": int(args.min_cjk_mixed_total),
                "min_commerce_case_total": int(args.min_commerce_case_total),
                "max_invalid_case_total": int(args.max_invalid_case_total),
                "max_case_total_drop": int(args.max_case_total_drop),
                "max_missing_attack_type_total_increase": int(args.max_missing_attack_type_total_increase),
                "max_korean_case_ratio_drop": float(args.max_korean_case_ratio_drop),
                "max_cjk_mixed_total_drop": int(args.max_cjk_mixed_total_drop),
                "max_commerce_case_total_drop": int(args.max_commerce_case_total_drop),
                "max_invalid_case_total_increase": int(args.max_invalid_case_total_increase),
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
    print(f"gate_pass={str(payload['gate']['pass']).lower()}")

    if args.gate and (failures or baseline_failures):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
