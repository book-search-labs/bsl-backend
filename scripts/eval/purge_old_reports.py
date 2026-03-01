#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

_REPORT_STEM_PATTERN = re.compile(r"^(?P<prefix>.+)_(?P<stamp>\d{8}_\d{6})$")


class ReportEntry(NamedTuple):
    prefix: str
    stamp: str
    generated_at: datetime
    files: tuple[Path, ...]


def parse_report_stem(stem: str) -> tuple[str, str, datetime] | None:
    match = _REPORT_STEM_PATTERN.match(stem)
    if not match:
        return None
    prefix = str(match.group("prefix") or "").strip()
    stamp = str(match.group("stamp") or "").strip()
    if not prefix or not stamp:
        return None
    try:
        generated_at = datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return prefix, stamp, generated_at


def collect_entries(reports_dir: Path, allowed_prefixes: set[str] | None = None) -> list[ReportEntry]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(reports_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix not in {".json", ".md"}:
            continue
        parsed = parse_report_stem(path.stem)
        if parsed is None:
            continue
        prefix, stamp, generated_at = parsed
        if allowed_prefixes and prefix not in allowed_prefixes:
            continue
        key = (prefix, stamp)
        bucket = grouped.setdefault(
            key,
            {
                "prefix": prefix,
                "stamp": stamp,
                "generated_at": generated_at,
                "files": [],
            },
        )
        bucket_files = bucket.get("files")
        if isinstance(bucket_files, list):
            bucket_files.append(path)

    entries: list[ReportEntry] = []
    for data in grouped.values():
        files_raw = data.get("files")
        files = tuple(sorted(files_raw)) if isinstance(files_raw, list) else tuple()
        entries.append(
            ReportEntry(
                prefix=str(data.get("prefix") or ""),
                stamp=str(data.get("stamp") or ""),
                generated_at=data.get("generated_at") if isinstance(data.get("generated_at"), datetime) else datetime.now(timezone.utc),
                files=files,
            )
        )
    entries.sort(key=lambda item: (item.prefix, item.generated_at, item.stamp), reverse=True)
    return entries


def plan_purge(
    entries: list[ReportEntry],
    *,
    now: datetime,
    retention_days: int,
    keep_latest_per_prefix: int,
) -> dict[str, Any]:
    cutoff = now - timedelta(days=max(0, int(retention_days)))
    grouped: dict[str, list[ReportEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.prefix, []).append(entry)

    delete_entries: list[ReportEntry] = []
    keep_entries: list[dict[str, Any]] = []
    per_prefix: dict[str, dict[str, int]] = {}

    for prefix, items in grouped.items():
        sorted_items = sorted(items, key=lambda item: (item.generated_at, item.stamp), reverse=True)
        prefix_kept = 0
        prefix_deleted = 0
        for index, entry in enumerate(sorted_items):
            if index < keep_latest_per_prefix:
                prefix_kept += 1
                keep_entries.append(
                    {
                        "prefix": prefix,
                        "stamp": entry.stamp,
                        "generated_at": entry.generated_at.isoformat(),
                        "reason": "keep_latest",
                        "files": [str(path) for path in entry.files],
                    }
                )
                continue
            if entry.generated_at < cutoff:
                prefix_deleted += 1
                delete_entries.append(entry)
                continue
            prefix_kept += 1
            keep_entries.append(
                {
                    "prefix": prefix,
                    "stamp": entry.stamp,
                    "generated_at": entry.generated_at.isoformat(),
                    "reason": "within_retention",
                    "files": [str(path) for path in entry.files],
                }
            )
        per_prefix[prefix] = {
            "total_entries": len(sorted_items),
            "kept_entries": prefix_kept,
            "deleted_entries": prefix_deleted,
        }

    return {
        "cutoff": cutoff,
        "delete_entries": delete_entries,
        "keep_entries": keep_entries,
        "per_prefix": per_prefix,
    }


def execute_purge(plan: dict[str, Any], *, dry_run: bool) -> tuple[list[str], list[str]]:
    deleted_files: list[str] = []
    errors: list[str] = []
    delete_entries = plan.get("delete_entries") if isinstance(plan.get("delete_entries"), list) else []
    for entry in delete_entries:
        if not isinstance(entry, ReportEntry):
            continue
        for file_path in entry.files:
            file_str = str(file_path)
            if dry_run:
                deleted_files.append(file_str)
                continue
            try:
                file_path.unlink(missing_ok=True)
            except Exception as exc:  # pragma: no cover - defensive path
                errors.append(f"{file_str}: {exc}")
                continue
            deleted_files.append(file_str)
    return deleted_files, errors


def render_summary(
    *,
    reports_dir: Path,
    entries: list[ReportEntry],
    plan: dict[str, Any],
    dry_run: bool,
    retention_days: int,
    keep_latest_per_prefix: int,
    deleted_files: list[str],
    errors: list[str],
    prefixes: list[str],
) -> dict[str, Any]:
    delete_entries = plan.get("delete_entries") if isinstance(plan.get("delete_entries"), list) else []
    delete_entry_payload: list[dict[str, Any]] = []
    for entry in delete_entries:
        if not isinstance(entry, ReportEntry):
            continue
        delete_entry_payload.append(
            {
                "prefix": entry.prefix,
                "stamp": entry.stamp,
                "generated_at": entry.generated_at.isoformat(),
                "files": [str(path) for path in entry.files],
            }
        )

    return {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reports_dir": str(reports_dir),
        "dry_run": bool(dry_run),
        "retention_days": int(retention_days),
        "keep_latest_per_prefix": int(keep_latest_per_prefix),
        "prefixes": prefixes,
        "totals": {
            "total_entries": len(entries),
            "total_files": sum(len(entry.files) for entry in entries),
            "delete_entries": len(delete_entry_payload),
            "delete_files": len(deleted_files),
            "errors": len(errors),
        },
        "cutoff": plan.get("cutoff").isoformat() if isinstance(plan.get("cutoff"), datetime) else None,
        "per_prefix": plan.get("per_prefix") if isinstance(plan.get("per_prefix"), dict) else {},
        "delete_entries": delete_entry_payload,
        "keep_entries": plan.get("keep_entries") if isinstance(plan.get("keep_entries"), list) else [],
        "deleted_files": deleted_files,
        "errors": errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Purge old timestamped eval reports by retention policy.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--retention-days", type=int, default=14)
    parser.add_argument("--keep-latest-per-prefix", type=int, default=3)
    parser.add_argument("--prefix", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-json", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    allowed_prefixes = {
        str(item).strip() for item in list(args.prefix or []) if str(item).strip()
    }

    if not reports_dir.exists():
        summary = {
            "version": "v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reports_dir": str(reports_dir),
            "status": "reports_dir_missing",
            "dry_run": bool(args.dry_run),
            "retention_days": max(0, int(args.retention_days)),
            "keep_latest_per_prefix": max(0, int(args.keep_latest_per_prefix)),
            "prefixes": sorted(allowed_prefixes),
            "totals": {"total_entries": 0, "total_files": 0, "delete_entries": 0, "delete_files": 0, "errors": 0},
        }
        print(json.dumps(summary, ensure_ascii=True, indent=2))
        return 0

    entries = collect_entries(reports_dir, allowed_prefixes=allowed_prefixes or None)
    plan = plan_purge(
        entries,
        now=datetime.now(timezone.utc),
        retention_days=max(0, int(args.retention_days)),
        keep_latest_per_prefix=max(0, int(args.keep_latest_per_prefix)),
    )
    deleted_files, errors = execute_purge(plan, dry_run=bool(args.dry_run))

    summary = render_summary(
        reports_dir=reports_dir,
        entries=entries,
        plan=plan,
        dry_run=bool(args.dry_run),
        retention_days=max(0, int(args.retention_days)),
        keep_latest_per_prefix=max(0, int(args.keep_latest_per_prefix)),
        deleted_files=deleted_files,
        errors=errors,
        prefixes=sorted(allowed_prefixes),
    )

    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] wrote summary json -> {summary_path}")

    print(json.dumps(summary, ensure_ascii=True, indent=2))

    if errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
