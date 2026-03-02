#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def resolve_cycle_reports(reports_dir: Path, *, prefix: str, limit: int) -> list[Path]:
    rows = sorted(reports_dir.glob(f"{prefix}_*.json"), key=lambda item: item.stat().st_mtime)
    return rows[-max(1, int(limit)) :]


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


def _duration_sec(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    if end < start:
        return None
    return (end - start).total_seconds()


def build_incident_summary(paths: list[Path]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    detection_latencies: list[float] = []
    incidents: list[dict[str, Any]] = []
    open_incident: dict[str, Any] | None = None

    for path in paths:
        payload = load_json(path)
        cycle_at = _parse_ts(payload.get("generated_at"))
        launch = payload.get("launch_gate") if isinstance(payload.get("launch_gate"), Mapping) else {}
        launch_at = _parse_ts(launch.get("generated_at"))
        decision_root = payload.get("release_train") if isinstance(payload.get("release_train"), Mapping) else {}
        decision = decision_root.get("decision") if isinstance(decision_root.get("decision"), Mapping) else {}
        action = str(decision.get("action") or "unknown")
        passed = not bool(payload.get("failures"))
        event = {
            "path": str(path),
            "generated_at": str(payload.get("generated_at") or ""),
            "action": action,
            "pass": passed,
        }
        det = _duration_sec(launch_at, cycle_at)
        if det is not None:
            event["detection_latency_sec"] = det
            detection_latencies.append(det)
        events.append(event)

        if action == "rollback":
            if open_incident is None:
                open_incident = {
                    "opened_at": str(payload.get("generated_at") or ""),
                    "opened_path": str(path),
                    "reason": str(decision.get("reason") or ""),
                }
            continue
        if action == "promote" and passed and open_incident is not None:
            opened_dt = _parse_ts(open_incident.get("opened_at"))
            resolved_dt = cycle_at
            mttr = _duration_sec(opened_dt, resolved_dt)
            incident = dict(open_incident)
            incident["resolved_at"] = str(payload.get("generated_at") or "")
            incident["resolved_path"] = str(path)
            incident["mttr_sec"] = mttr
            incidents.append(incident)
            open_incident = None

    mttr_values = [float(item.get("mttr_sec")) for item in incidents if isinstance(item.get("mttr_sec"), (int, float))]
    mtta = 0.0 if not detection_latencies else float(sum(detection_latencies)) / float(len(detection_latencies))
    mttr = 0.0 if not mttr_values else float(sum(mttr_values)) / float(len(mttr_values))

    return {
        "window_size": len(paths),
        "event_total": len(events),
        "incident_total": len(incidents),
        "open_incident_total": 1 if open_incident is not None else 0,
        "mtta_sec": mtta,
        "mttr_sec": mttr,
        "detection_latency_samples": detection_latencies[-20:],
        "events": events[-20:],
        "incidents": incidents[-20:],
        "open_incident": open_incident,
    }


def evaluate_gate(summary: Mapping[str, Any], *, min_window: int, max_mtta_sec: float, max_mttr_sec: float, max_open_incidents: int) -> list[str]:
    failures: list[str] = []
    window_size = int(summary.get("window_size") or 0)
    mtta_sec = float(summary.get("mtta_sec") or 0.0)
    mttr_sec = float(summary.get("mttr_sec") or 0.0)
    open_incident_total = int(summary.get("open_incident_total") or 0)

    if window_size < max(0, int(min_window)):
        failures.append(f"insufficient liveops cycle samples: window_size={window_size} < min_window={min_window}")
    if mtta_sec > max(0.0, float(max_mtta_sec)):
        failures.append(f"mtta exceeded: {mtta_sec:.2f}s > {float(max_mtta_sec):.2f}s")
    if mttr_sec > max(0.0, float(max_mttr_sec)):
        failures.append(f"mttr exceeded: {mttr_sec:.2f}s > {float(max_mttr_sec):.2f}s")
    if open_incident_total > max(0, int(max_open_incidents)):
        failures.append(f"open incidents exceeded: {open_incident_total} > {int(max_open_incidents)}")

    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize MTTA/MTTR from liveops cycle reports and evaluate incident gate.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_liveops_cycle")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-window", type=int, default=3)
    parser.add_argument("--max-mtta-sec", type=float, default=600.0)
    parser.add_argument("--max-mttr-sec", type=float, default=7200.0)
    parser.add_argument("--max-open-incidents", type=int, default=0)
    parser.add_argument("--gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    paths = resolve_cycle_reports(reports_dir, prefix=str(args.prefix), limit=max(1, int(args.limit)))
    summary = build_incident_summary(paths)
    failures = evaluate_gate(
        summary,
        min_window=max(0, int(args.min_window)),
        max_mtta_sec=max(0.0, float(args.max_mtta_sec)),
        max_mttr_sec=max(0.0, float(args.max_mttr_sec)),
        max_open_incidents=max(0, int(args.max_open_incidents)),
    )
    payload = {
        "summary": summary,
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_window": int(args.min_window),
                "max_mtta_sec": float(args.max_mtta_sec),
                "max_mttr_sec": float(args.max_mttr_sec),
                "max_open_incidents": int(args.max_open_incidents),
            },
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.gate and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
