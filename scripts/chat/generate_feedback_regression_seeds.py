#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            loaded = json.loads(line)
            if isinstance(loaded, dict):
                rows.append(loaded)
    return rows


def _normalize_reason(reason: Any) -> str:
    text = str(reason or "").strip().upper()
    return text or "UNKNOWN"


def _slug(text: str) -> str:
    lowered = text.lower()
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_") or "seed"


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def _scenario_stub_for_reason(reason_code: str) -> dict[str, Any]:
    reason = _normalize_reason(reason_code)
    scenario_id = f"F_{_slug(reason)}"
    if reason in {"AUTH_REQUIRED", "NEED_AUTH:USER_LOGIN"}:
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "주문 12 상태 알려줘",
                    "user_id": None,
                    "expected": {"status": "needs_auth", "reason_code": "AUTH_REQUIRED"},
                }
            ],
        }
    if reason.startswith("NEED_SLOT:ORDER_REF"):
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "내 주문 상태 알려줘",
                    "user_id": "1",
                    "expected": {"status": "needs_input", "reason_code": "NEED_SLOT:ORDER_REF"},
                }
            ],
        }
    if reason == "MISSING_REQUIRED_INFO":
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "문의 접수해줘",
                    "user_id": "1",
                    "expected": {"status": "needs_input", "reason_code": "MISSING_REQUIRED_INFO"},
                }
            ],
        }
    if reason == "MISSING_INPUT":
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "그거 해줘",
                    "user_id": None,
                    "expected": {"status": "needs_input", "reason_code": "MISSING_INPUT"},
                }
            ],
        }
    if reason in {"TOOL_RETRYABLE_FAILURE", "TOOL_TIMEOUT", "PROVIDER_TIMEOUT"}:
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "주문 12 환불 신청해줘",
                    "user_id": "1",
                    "capture_token": True,
                    "expected": {"reason_code": "CONFIRMATION_REQUIRED"},
                },
                {
                    "query": "확인 {{token}}",
                    "user_id": "1",
                    "expected": {"status": "tool_fallback", "reason_code": "TOOL_RETRYABLE_FAILURE"},
                },
            ],
        }
    if reason in {"AUTH_FORBIDDEN", "FORBIDDEN"}:
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "주문 12 취소해줘",
                    "user_id": "1",
                    "capture_token": True,
                    "expected": {"reason_code": "CONFIRMATION_REQUIRED"},
                },
                {
                    "query": "확인 {{token}}",
                    "user_id": "2",
                    "expected": {"status": "forbidden", "reason_code": "AUTH_FORBIDDEN"},
                },
            ],
        }
    if reason == "RESOURCE_NOT_FOUND":
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "주문 999999 상태 알려줘",
                    "user_id": "1",
                    "expected": {"status": "not_found", "reason_code": "RESOURCE_NOT_FOUND"},
                }
            ],
        }
    if reason in {"RATE_LIMITED", "LLM_CALL_RATE_LIMITED"}:
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "문의 접수해줘 결제가 안돼",
                    "user_id": "1",
                    "expected": {"reason_code": "OK"},
                },
                {
                    "query": "문의 접수해줘 결제가 안돼",
                    "user_id": "1",
                    "expected": {"reason_code": "RATE_LIMITED"},
                },
            ],
        }
    if reason in {"CONFIRMATION_EXPIRED", "USER_ABORTED"}:
        return {
            "id": scenario_id,
            "turns": [
                {
                    "query": "주문 12 취소해줘",
                    "user_id": "1",
                    "capture_token": True,
                    "expected": {"reason_code": "CONFIRMATION_REQUIRED"},
                },
                {
                    "query": "중단",
                    "user_id": "1",
                    "expected": {"reason_code": "USER_ABORTED" if reason == "USER_ABORTED" else "CONFIRMATION_EXPIRED"},
                },
            ],
        }
    return {
        "id": scenario_id,
        "turns": [
            {
                "query": "TODO: 실제 사용자 재현 질의를 입력하세요",
                "user_id": "1",
                "expected": {"reason_code": reason},
            }
        ],
    }


def build_seed_payload(
    records: list[dict[str, Any]],
    *,
    min_reason_count: int,
    max_items: int,
) -> dict[str, Any]:
    reason_counts: dict[str, int] = {}
    negative = 0
    hallucination = 0
    insufficient = 0
    for item in records:
        rating = str(item.get("rating") or "").strip().lower()
        is_negative = rating == "down"
        if is_negative:
            negative += 1
            reason = _normalize_reason(item.get("reason_code"))
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if _is_true(item.get("flag_hallucination")):
            hallucination += 1
        if _is_true(item.get("flag_insufficient")):
            insufficient += 1

    ranked = sorted(reason_counts.items(), key=lambda row: (-int(row[1]), row[0]))
    picked = [row for row in ranked if row[1] >= max(1, min_reason_count)][: max(1, max_items)]

    items: list[dict[str, Any]] = []
    for reason, count in picked:
        stub = _scenario_stub_for_reason(reason)
        items.append(
            {
                "id": f"feedback.reason.{_slug(reason)}",
                "reason_code": reason,
                "count": int(count),
                "title": f"Feedback spike reason: {reason}",
                "suggested_ticket": "B-0623",
                "owner": "chat-regression",
                "scenario_stub": stub,
            }
        )

    return {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_records": len(records),
            "negative_records": negative,
            "hallucination_flags": hallucination,
            "insufficient_flags": insufficient,
            "unique_reasons": len(reason_counts),
        },
        "thresholds": {
            "min_reason_count": max(1, int(min_reason_count)),
            "max_items": max(1, int(max_items)),
        },
        "reason_counts": reason_counts,
        "items": items,
    }


def render_markdown(payload: dict[str, Any], *, source: str) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    lines: list[str] = []
    lines.append("# Chat Feedback Regression Seeds")
    lines.append("")
    lines.append(f"- source: `{source}`")
    lines.append(f"- generated_at: `{payload.get('generated_at')}`")
    lines.append(f"- total_records: {int(summary.get('total_records') or 0)}")
    lines.append(f"- negative_records: {int(summary.get('negative_records') or 0)}")
    lines.append(f"- hallucination_flags: {int(summary.get('hallucination_flags') or 0)}")
    lines.append(f"- insufficient_flags: {int(summary.get('insufficient_flags') or 0)}")
    lines.append("")
    if not items:
        lines.append("- no seed candidates")
        return "\n".join(lines)

    for idx, item in enumerate(items, start=1):
        lines.append(f"## {idx}. {item.get('title')}")
        lines.append("")
        lines.append(f"- reason_code: `{item.get('reason_code')}`")
        lines.append(f"- count: {int(item.get('count') or 0)}")
        lines.append(f"- suggested_ticket: `{item.get('suggested_ticket')}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(item.get("scenario_stub"), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate chat regression seed candidates from feedback JSONL.")
    parser.add_argument("--input", default="evaluation/chat/feedback.jsonl")
    parser.add_argument("--output-json", default="evaluation/chat/feedback_regression_seeds.json")
    parser.add_argument("--output-md", default="tasks/backlog/generated/chat_feedback_regression_seeds.md")
    parser.add_argument("--min-reason-count", type=int, default=3)
    parser.add_argument("--max-items", type=int, default=12)
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    source = Path(args.input)
    rows = load_jsonl(source)
    if not rows and not args.allow_empty:
        print("[FAIL] no feedback records")
        return 1

    payload = build_seed_payload(
        rows,
        min_reason_count=max(1, int(args.min_reason_count)),
        max_items=max(1, int(args.max_items)),
    )

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote regression seed json -> {output_json}")

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(payload, source=str(source)), encoding="utf-8")
    print(f"[OK] wrote regression seed markdown -> {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
