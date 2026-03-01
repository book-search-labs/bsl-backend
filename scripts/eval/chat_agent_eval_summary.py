import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_COMPONENTS = {
    "recommend": "chat_recommend_eval_",
    "rollout": "chat_rollout_eval_",
    "semantic_cache": "chat_semantic_cache_eval_",
    "regression_suite": "chat_regression_suite_eval_",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return data


def find_latest_report(report_dir: Path, prefix: str) -> Path | None:
    candidates = sorted(report_dir.glob(f"{prefix}*.json"))
    return candidates[-1] if candidates else None


def summarize_components(report_dir: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, prefix in _COMPONENTS.items():
        latest = find_latest_report(report_dir, prefix)
        if latest is None:
            summary[name] = {
                "present": False,
                "path": None,
                "generated_at": None,
                "gate_pass": None,
                "failures": [],
            }
            continue
        payload = load_json(latest)
        gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
        failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
        baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
        merged_failures = [str(item) for item in (failures + baseline_failures)]
        summary[name] = {
            "present": True,
            "path": str(latest),
            "generated_at": payload.get("generated_at"),
            "gate_pass": bool(gate.get("pass")) if isinstance(gate.get("pass"), bool) else None,
            "failures": merged_failures,
        }
    return summary


def evaluate_overall(summary: dict[str, Any], *, require_all: bool) -> tuple[bool, list[str]]:
    failures: list[str] = []
    overall_pass = True
    for name in sorted(_COMPONENTS.keys()):
        component = summary.get(name) if isinstance(summary.get(name), dict) else {}
        present = bool(component.get("present"))
        if not present:
            if require_all:
                overall_pass = False
                failures.append(f"missing component report: {name}")
            continue
        gate_pass = component.get("gate_pass")
        if gate_pass is False:
            overall_pass = False
            comp_failures = component.get("failures") if isinstance(component.get("failures"), list) else []
            if comp_failures:
                for item in comp_failures:
                    failures.append(f"{name}: {item}")
            else:
                failures.append(f"{name}: gate failed")
    return overall_pass, failures


def _parse_iso_datetime(text: Any) -> datetime | None:
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate_freshness(summary: dict[str, Any], *, max_age_minutes: int) -> list[str]:
    if max_age_minutes <= 0:
        return []
    failures: list[str] = []
    now = datetime.now(timezone.utc)
    max_age_sec = max_age_minutes * 60
    for name in sorted(_COMPONENTS.keys()):
        component = summary.get(name) if isinstance(summary.get(name), dict) else {}
        if not bool(component.get("present")):
            continue
        generated_at = _parse_iso_datetime(component.get("generated_at"))
        if generated_at is None:
            failures.append(f"{name}: invalid generated_at")
            continue
        age_sec = (now - generated_at).total_seconds()
        if age_sec > float(max_age_sec):
            failures.append(f"{name}: stale report age_sec={int(age_sec)} > max_age_sec={int(max_age_sec)}")
    return failures


def render_markdown(report: dict[str, Any]) -> str:
    components = report.get("components") if isinstance(report.get("components"), dict) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    lines: list[str] = []
    lines.append("# Chat Agent Eval Summary")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- reports_dir: {report.get('source', {}).get('reports_dir')}")
    lines.append("")
    lines.append("| Component | Present | Gate | Generated At |")
    lines.append("| --- | --- | --- | --- |")
    for name in sorted(_COMPONENTS.keys()):
        comp = components.get(name) if isinstance(components.get(name), dict) else {}
        present = "yes" if comp.get("present") else "no"
        gate_pass = comp.get("gate_pass")
        gate_text = "pass" if gate_pass is True else ("fail" if gate_pass is False else "n/a")
        generated_at = str(comp.get("generated_at") or "-")
        lines.append(f"| {name} | {present} | {gate_text} | {generated_at} |")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    if failures:
        lines.append("- failures:")
        for item in failures:
            lines.append(f"  - {item}")
    else:
        lines.append("- failures: none")
    return "\n".join(lines)


def build_metric_snapshot(components: dict[str, Any], *, gate_pass: bool) -> dict[str, float]:
    metrics: dict[str, float] = {}
    metrics["chat_agent_eval_summary_gate_pass"] = 1.0 if gate_pass else 0.0
    for name in sorted(_COMPONENTS.keys()):
        comp = components.get(name) if isinstance(components.get(name), dict) else {}
        present = bool(comp.get("present"))
        gate = comp.get("gate_pass")
        metrics[f"chat_agent_eval_component_present{{component={name}}}"] = 1.0 if present else 0.0
        if gate is True:
            metrics[f"chat_agent_eval_component_gate_pass{{component={name}}}"] = 1.0
        elif gate is False:
            metrics[f"chat_agent_eval_component_gate_pass{{component={name}}}"] = 0.0
    return metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize chat eval reports into one gate snapshot.")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_agent_eval_summary")
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--max-age-minutes", type=int, default=0)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    components = summarize_components(reports_dir)
    overall_pass, failures = evaluate_overall(components, require_all=bool(args.require_all))
    freshness_failures = evaluate_freshness(components, max_age_minutes=max(0, int(args.max_age_minutes)))
    if freshness_failures:
        overall_pass = False
        failures.extend(freshness_failures)

    report = {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"reports_dir": str(reports_dir)},
        "components": components,
        "metrics": build_metric_snapshot(components, gate_pass=overall_pass),
        "gate": {
            "pass": overall_pass,
            "failures": failures,
            "require_all": bool(args.require_all),
            "max_age_minutes": max(0, int(args.max_age_minutes)),
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{timestamp}.json"
    md_path = out_dir / f"{args.prefix}_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    if args.write_baseline:
        baseline_path = Path(args.write_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[chat_agent_eval_summary] report(json): {json_path}")
    print(f"[chat_agent_eval_summary] report(md): {md_path}")
    print(f"[chat_agent_eval_summary] gate_pass={str(overall_pass).lower()}")

    if args.gate and not overall_pass:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
