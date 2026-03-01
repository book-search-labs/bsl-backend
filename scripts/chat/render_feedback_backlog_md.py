#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def render_markdown(payload: dict[str, Any]) -> str:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
    generated_at = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())
    source = str(payload.get("source") or "unknown")
    total = int(payload.get("total") or 0)

    lines: list[str] = []
    lines.append("# Chat Feedback Backlog (Auto)")
    lines.append("")
    lines.append(f"- generated_at: {generated_at}")
    lines.append(f"- source: `{source}`")
    lines.append(f"- total_feedback: {total}")
    if thresholds:
        lines.append("- thresholds:")
        for key in sorted(thresholds.keys()):
            lines.append(f"  - {key}: {thresholds[key]}")
    lines.append("")
    lines.append("## Suggested Tickets")
    lines.append("")
    if not items:
        lines.append("- No backlog items generated.")
        return "\n".join(lines)

    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "Untitled")
        priority = str(raw.get("priority") or "medium")
        metric = str(raw.get("metric") or "unknown")
        value = raw.get("value")
        threshold = raw.get("threshold")
        suggested = str(raw.get("suggested_ticket") or "N/A")
        owner = str(raw.get("owner") or "chat")
        item_id = str(raw.get("id") or f"item-{idx}")

        lines.append(f"### {idx}. {title}")
        lines.append(f"- id: `{item_id}`")
        lines.append(f"- priority: `{priority}`")
        lines.append(f"- owner: `{owner}`")
        lines.append(f"- suggested_ticket: `{suggested}`")
        lines.append(f"- signal: `{metric}` value={value} threshold={threshold}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render feedback backlog JSON into markdown ticket draft.")
    parser.add_argument("--input", default="evaluation/chat/feedback_backlog.json")
    parser.add_argument("--output", default="tasks/backlog/generated/chat_feedback_auto.md")
    args = parser.parse_args()

    payload = load_json(Path(args.input))
    markdown = render_markdown(payload)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"[OK] wrote markdown backlog -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
