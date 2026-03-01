import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return data


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return data


def parse_metric_key(key: str) -> Tuple[str, dict[str, str]]:
    text = str(key or "").strip()
    if not text:
        return "", {}
    if "{" not in text or not text.endswith("}"):
        return text, {}
    name, raw_labels = text.split("{", 1)
    labels_text = raw_labels[:-1]
    labels: dict[str, str] = {}
    for pair in labels_text.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        label_key, label_val = pair.split("=", 1)
        labels[label_key.strip()] = label_val.strip()
    return name.strip(), labels


def collect_rollout_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    traffic: dict[str, float] = {}
    gate_totals: dict[str, dict[str, float]] = {}
    rollback_total = 0.0
    reset_total = 0.0
    failure_ratio_agent: float | None = None

    for key, value in (snapshot or {}).items():
        name, labels = parse_metric_key(str(key))
        metric_value = _to_float(value)
        if name == "chat_rollout_traffic_ratio":
            engine = labels.get("engine", "unknown")
            traffic[engine] = traffic.get(engine, 0.0) + metric_value
            continue
        if name == "chat_rollout_gate_total":
            engine = labels.get("engine", "unknown")
            result = labels.get("result", "unknown")
            if engine not in gate_totals:
                gate_totals[engine] = {}
            gate_totals[engine][result] = gate_totals[engine].get(result, 0.0) + metric_value
            continue
        if name == "chat_rollout_rollback_total":
            rollback_total += metric_value
            continue
        if name == "chat_rollout_reset_total":
            reset_total += metric_value
            continue
        if name == "chat_rollout_failure_ratio" and labels.get("engine") == "agent":
            failure_ratio_agent = metric_value

    agent_gate = gate_totals.get("agent", {})
    agent_pass = _to_float(agent_gate.get("pass", 0.0))
    agent_rollback = _to_float(agent_gate.get("rollback", 0.0))
    agent_observed = agent_pass + agent_rollback

    return {
        "traffic": traffic,
        "gate_totals": gate_totals,
        "failure_ratio_agent": 0.0 if failure_ratio_agent is None else failure_ratio_agent,
        "failure_ratio_source": "gauge" if failure_ratio_agent is not None else "default_zero",
        "rollback_total": rollback_total,
        "reset_total": reset_total,
        "agent_gate": {
            "pass": agent_pass,
            "rollback": agent_rollback,
            "observed": agent_observed,
        },
    }


def evaluate_gate(
    derived: dict[str, Any],
    *,
    max_failure_ratio: float,
    max_rollback_total: float,
    require_min_samples: bool,
    min_agent_samples: int,
    active_rollback: bool,
    allow_active_rollback: bool,
) -> list[str]:
    failures: list[str] = []
    ratio = _to_float(derived.get("failure_ratio_agent", 0.0))
    rollbacks = _to_float(derived.get("rollback_total", 0.0))
    agent_gate = derived.get("agent_gate") if isinstance(derived.get("agent_gate"), dict) else {}
    observed = _to_float(agent_gate.get("observed", 0.0))

    if require_min_samples and observed < float(max(1, min_agent_samples)):
        failures.append(f"insufficient rollout gate sample: observed={observed:.0f} < min_agent_samples={min_agent_samples}")
    if observed > 0 and ratio > max_failure_ratio:
        failures.append(f"rollout failure ratio too high: failure_ratio={ratio:.4f} > {max_failure_ratio:.4f}")
    if rollbacks > max_rollback_total:
        failures.append(
            "rollout auto-rollback events exceed limit: "
            f"rollback_total={rollbacks:.0f} > {max_rollback_total:.0f}"
        )
    if active_rollback and not allow_active_rollback:
        failures.append("rollout snapshot indicates active_rollback=true")
    return failures


def compare_with_baseline(
    baseline_report: dict[str, Any],
    current_derived: dict[str, Any],
    *,
    max_failure_ratio_increase: float,
    max_rollback_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report, dict) else {}
    if not isinstance(base_derived, dict):
        return failures

    base_ratio = _to_float(base_derived.get("failure_ratio_agent", 0.0))
    curr_ratio = _to_float(current_derived.get("failure_ratio_agent", 0.0))
    if curr_ratio > base_ratio + max_failure_ratio_increase:
        failures.append(
            "failure ratio regression: "
            f"baseline={base_ratio:.4f}, current={curr_ratio:.4f}, "
            f"allowed_increase={max_failure_ratio_increase:.4f}"
        )

    base_rollbacks = _to_float(base_derived.get("rollback_total", 0.0))
    curr_rollbacks = _to_float(current_derived.get("rollback_total", 0.0))
    if curr_rollbacks > base_rollbacks + max_rollback_increase:
        failures.append(
            "rollback total regression: "
            f"baseline={base_rollbacks:.0f}, current={curr_rollbacks:.0f}, "
            f"allowed_increase={max_rollback_increase:.0f}"
        )
    return failures


def render_markdown(report: dict[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), dict) else {}
    traffic = derived.get("traffic") if isinstance(derived.get("traffic"), dict) else {}
    gate_totals = derived.get("gate_totals") if isinstance(derived.get("gate_totals"), dict) else {}
    agent_gate = derived.get("agent_gate") if isinstance(derived.get("agent_gate"), dict) else {}
    snapshot = report.get("rollout") if isinstance(report.get("rollout"), dict) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Rollout Eval Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- metrics_source: {report.get('source', {}).get('metrics')}")
    lines.append(f"- rollout_source: {report.get('source', {}).get('rollout')}")
    lines.append("")
    lines.append("## Rollout Snapshot")
    lines.append("")
    lines.append(f"- mode: {snapshot.get('mode')}")
    lines.append(f"- canary_percent: {snapshot.get('canary_percent')}")
    lines.append(f"- active_rollback: {bool(snapshot.get('active_rollback'))}")
    lines.append("")
    lines.append("## Traffic / Gate")
    lines.append("")
    lines.append(f"- traffic: {traffic}")
    lines.append(f"- gate_totals: {gate_totals}")
    lines.append(f"- agent_gate_observed: {agent_gate.get('observed', 0):.0f}")
    lines.append(f"- failure_ratio_agent: {derived.get('failure_ratio_agent', 0.0):.4f}")
    lines.append(f"- rollback_total: {derived.get('rollback_total', 0.0):.0f}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    if failures:
        lines.append("- failures:")
        for item in failures:
            lines.append(f"  - {item}")
    if baseline_failures:
        lines.append("- baseline_failures:")
        for item in baseline_failures:
            lines.append(f"  - {item}")
    if not failures and not baseline_failures:
        lines.append("- failures: none")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat rollout metrics and gate quality.")
    parser.add_argument("--metrics-url", default="http://localhost:8001/metrics")
    parser.add_argument("--metrics-json", default="")
    parser.add_argument("--rollout-url", default="http://localhost:8001/internal/chat/rollout")
    parser.add_argument("--rollout-json", default="")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_rollout_eval")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-agent-samples", type=int, default=20)
    parser.add_argument("--max-failure-ratio", type=float, default=0.2)
    parser.add_argument("--max-rollback-total", type=float, default=0.0)
    parser.add_argument("--require-min-samples", action="store_true")
    parser.add_argument("--allow-active-rollback", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-failure-ratio-increase", type=float, default=0.05)
    parser.add_argument("--max-rollback-increase", type=float, default=0.0)
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.metrics_json:
        metrics_snapshot = load_json(Path(args.metrics_json))
        metrics_source = str(Path(args.metrics_json))
    else:
        metrics_snapshot = fetch_json(args.metrics_url, args.timeout)
        metrics_source = args.metrics_url
    derived = collect_rollout_metrics(metrics_snapshot)

    rollout_snapshot: dict[str, Any] = {}
    rollout_source = None
    if args.rollout_json:
        payload = load_json(Path(args.rollout_json))
        rollout_snapshot = payload.get("rollout") if isinstance(payload.get("rollout"), dict) else {}
        rollout_source = str(Path(args.rollout_json))
    else:
        payload = fetch_json(args.rollout_url, args.timeout)
        rollout_snapshot = payload.get("rollout") if isinstance(payload.get("rollout"), dict) else {}
        rollout_source = args.rollout_url

    active_rollback = bool(rollout_snapshot.get("active_rollback"))
    failures = evaluate_gate(
        derived,
        max_failure_ratio=max(0.0, min(1.0, args.max_failure_ratio)),
        max_rollback_total=max(0.0, args.max_rollback_total),
        require_min_samples=bool(args.require_min_samples),
        min_agent_samples=max(1, args.min_agent_samples),
        active_rollback=active_rollback,
        allow_active_rollback=bool(args.allow_active_rollback),
    )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            derived,
            max_failure_ratio_increase=max(0.0, min(1.0, args.max_failure_ratio_increase)),
            max_rollback_increase=max(0.0, args.max_rollback_increase),
        )

    passed = not failures and not baseline_failures
    report = {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "metrics": metrics_source,
            "rollout": rollout_source,
            "baseline_report": args.baseline_report or None,
        },
        "thresholds": {
            "min_agent_samples": max(1, args.min_agent_samples),
            "max_failure_ratio": max(0.0, min(1.0, args.max_failure_ratio)),
            "max_rollback_total": max(0.0, args.max_rollback_total),
            "require_min_samples": bool(args.require_min_samples),
            "allow_active_rollback": bool(args.allow_active_rollback),
            "max_failure_ratio_increase": max(0.0, min(1.0, args.max_failure_ratio_increase)),
            "max_rollback_increase": max(0.0, args.max_rollback_increase),
        },
        "derived": derived,
        "rollout": rollout_snapshot,
        "gate": {
            "pass": passed,
            "failures": failures,
            "baseline_failures": baseline_failures,
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{ts}.json"
    md_path = out_dir / f"{args.prefix}_{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"[OK] report -> {json_path}")
    print(f"[OK] report -> {md_path}")

    if args.write_baseline:
        baseline_path = Path(args.write_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
        print(f"[OK] wrote baseline -> {baseline_path}")

    if not passed:
        print("[FAIL] rollout quality gate failed:")
        for item in failures:
            print(f"  - {item}")
        for item in baseline_failures:
            print(f"  - {item}")
        return 2 if args.gate else 0
    print("[OK] rollout quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
