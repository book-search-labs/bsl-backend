#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "item"


def _ticket_filename(item_id: str, title: str) -> str:
    return f"{_slugify(item_id)}--{_slugify(title)[:48]}.md"


def render_ticket(item: dict[str, Any], *, source: str, generated_at: str) -> str:
    item_id = str(item.get("id") or "unknown")
    title = str(item.get("title") or "Untitled")
    priority = str(item.get("priority") or "medium")
    owner = str(item.get("owner") or "chat")
    metric = str(item.get("metric") or "unknown")
    value = item.get("value")
    threshold = item.get("threshold")
    suggested = str(item.get("suggested_ticket") or "N/A")
    body: list[str] = []
    body.append(f"# AUTO-FEEDBACK — {title}")
    body.append("")
    body.append(f"- item_id: `{item_id}`")
    body.append(f"- priority: `{priority}`")
    body.append(f"- owner: `{owner}`")
    body.append(f"- suggested_ticket: `{suggested}`")
    body.append(f"- source: `{source}`")
    body.append(f"- generated_at: `{generated_at}`")
    body.append("")
    body.append("## Trigger")
    body.append(f"- metric: `{metric}`")
    body.append(f"- value: `{value}`")
    body.append(f"- threshold: `{threshold}`")
    body.append("")
    body.append("## Action Proposal")
    body.append(f"- Link this signal to `{suggested}` implementation/review flow.")
    body.append("- Validate regression impact with chat recommend/report gates before rollout.")
    body.append("")
    body.append("## Notes")
    body.append("- This file is auto-generated from chat feedback backlog pipeline.")
    body.append("- Manual edits may be overwritten by next sync run.")
    return "\n".join(body)


def render_index(files: list[tuple[str, dict[str, Any]]], *, source: str, generated_at: str) -> str:
    lines: list[str] = []
    lines.append("# AUTO-FEEDBACK Ticket Index")
    lines.append("")
    lines.append(f"- source: `{source}`")
    lines.append(f"- generated_at: `{generated_at}`")
    lines.append(f"- count: {len(files)}")
    lines.append("")
    if not files:
        lines.append("- no items")
        return "\n".join(lines)
    for filename, item in files:
        lines.append(f"- [{item.get('title')}]({filename})")
    return "\n".join(lines)


def sync_tickets(
    payload: dict[str, Any],
    *,
    output_dir: Path,
    prune: bool,
) -> tuple[int, int]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    source = str(payload.get("source") or "unknown")
    generated_at = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())
    output_dir.mkdir(parents=True, exist_ok=True)

    wanted_files: dict[str, dict[str, Any]] = {}
    written = 0
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not item_id or not title:
            continue
        filename = _ticket_filename(item_id, title)
        wanted_files[filename] = raw
        content = render_ticket(raw, source=source, generated_at=generated_at)
        target = output_dir / filename
        previous = target.read_text(encoding="utf-8") if target.exists() else None
        if previous != content:
            target.write_text(content, encoding="utf-8")
            written += 1

    index_content = render_index(sorted(wanted_files.items(), key=lambda item: item[0]), source=source, generated_at=generated_at)
    index_path = output_dir / "_index.md"
    previous_index = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    if previous_index != index_content:
        index_path.write_text(index_content, encoding="utf-8")
        written += 1

    removed = 0
    if prune:
        for path in output_dir.glob("*.md"):
            if path.name == "_index.md":
                continue
            if path.name not in wanted_files:
                path.unlink(missing_ok=True)
                removed += 1
    return written, removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync feedback backlog items into generated markdown tickets.")
    parser.add_argument("--input", default="evaluation/chat/feedback_backlog.json")
    parser.add_argument("--output-dir", default="tasks/backlog/generated/feedback")
    parser.add_argument("--no-prune", action="store_true")
    args = parser.parse_args()

    payload = load_json(Path(args.input))
    output_dir = Path(args.output_dir)
    written, removed = sync_tickets(payload, output_dir=output_dir, prune=not bool(args.no_prune))
    print(f"[OK] synced feedback tickets -> {output_dir} (written={written}, removed={removed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
