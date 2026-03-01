import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


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


def _variant_counts(totals: dict[str, dict[str, float]], variant: str) -> dict[str, float]:
    source = totals.get(variant, {})
    return {
        "assigned": _to_float(source.get("assigned", 0.0)),
        "served": _to_float(source.get("served", 0.0)),
        "blocked": _to_float(source.get("blocked", 0.0)),
        "auto_disabled": _to_float(source.get("auto_disabled", 0.0)),
    }


def collect_recommend_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    totals: dict[str, dict[str, float]] = {}
    quality_blocks: dict[str, float] = {}
    block_rate_gauge: float | None = None
    auto_disable_total = 0.0

    for key, value in (snapshot or {}).items():
        name, labels = parse_metric_key(str(key))
        metric_value = _to_float(value)
        if name == "chat_recommend_experiment_total":
            variant = labels.get("variant", "unknown")
            status = labels.get("status", "unknown")
            if variant not in totals:
                totals[variant] = {}
            totals[variant][status] = totals[variant].get(status, 0.0) + metric_value
            continue
        if name == "chat_recommend_quality_gate_block_total":
            reason = labels.get("reason", "unknown")
            quality_blocks[reason] = quality_blocks.get(reason, 0.0) + metric_value
            continue
        if name == "chat_recommend_experiment_auto_disable_total":
            auto_disable_total += metric_value
            continue
        if name == "chat_recommend_experiment_block_rate" and labels.get("variant") == "diversity":
            block_rate_gauge = metric_value

    diversity = _variant_counts(totals, "diversity")
    baseline = _variant_counts(totals, "baseline")
    observed = diversity["served"] + diversity["blocked"]
    calculated_block_rate = (diversity["blocked"] / observed) if observed > 0 else 0.0
    block_rate = block_rate_gauge if block_rate_gauge is not None else calculated_block_rate

    return {
        "totals": totals,
        "quality_blocks": quality_blocks,
        "overall_auto_disable_total": auto_disable_total,
        "diversity": {
            **diversity,
            "observed": observed,
            "block_rate": block_rate,
            "block_rate_source": "gauge" if block_rate_gauge is not None else "calculated",
        },
        "baseline": baseline,
    }


def evaluate_gate(
    derived: dict[str, Any],
    *,
    min_samples: int,
    max_block_rate: float,
    max_auto_disable_total: float,
    require_min_samples: bool,
    session_auto_disabled: bool,
) -> list[str]:
    failures: list[str] = []
    diversity = derived.get("diversity") if isinstance(derived, dict) else {}
    if not isinstance(diversity, dict):
        diversity = {}
    observed = _to_float(diversity.get("observed", 0.0))
    block_rate = _to_float(diversity.get("block_rate", 0.0))
    auto_disable_total = _to_float(derived.get("overall_auto_disable_total", 0.0))

    if require_min_samples and observed < float(max(1, min_samples)):
        failures.append(f"insufficient diversity sample: observed={observed:.0f} < min_samples={min_samples}")
    if observed > 0 and block_rate > max_block_rate:
        failures.append(f"quality block rate too high: block_rate={block_rate:.4f} > {max_block_rate:.4f}")
    if auto_disable_total > max_auto_disable_total:
        failures.append(
            "auto-disable events exceed limit: "
            f"auto_disable_total={auto_disable_total:.0f} > {max_auto_disable_total:.0f}"
        )
    if session_auto_disabled:
        failures.append("session snapshot indicates experiment auto_disabled=true")
    return failures


def compare_with_baseline(
    baseline_report: dict[str, Any],
    current_derived: dict[str, Any],
    *,
    max_block_rate_increase: float,
    max_auto_disable_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report, dict) else {}
    if not isinstance(base_derived, dict):
        return failures

    base_div = base_derived.get("diversity") if isinstance(base_derived.get("diversity"), dict) else {}
    curr_div = current_derived.get("diversity") if isinstance(current_derived.get("diversity"), dict) else {}
    base_block_rate = _to_float(base_div.get("block_rate", 0.0))
    curr_block_rate = _to_float(curr_div.get("block_rate", 0.0))
    if curr_block_rate > base_block_rate + max_block_rate_increase:
        failures.append(
            "block rate regression: "
            f"baseline={base_block_rate:.4f}, current={curr_block_rate:.4f}, "
            f"allowed_increase={max_block_rate_increase:.4f}"
        )

    base_auto = _to_float(base_derived.get("overall_auto_disable_total", 0.0))
    curr_auto = _to_float(current_derived.get("overall_auto_disable_total", 0.0))
    if curr_auto > base_auto + max_auto_disable_increase:
        failures.append(
            "auto-disable regression: "
            f"baseline={base_auto:.0f}, current={curr_auto:.0f}, "
            f"allowed_increase={max_auto_disable_increase:.0f}"
        )
    return failures


def render_markdown(report: dict[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), dict) else {}
    diversity = derived.get("diversity") if isinstance(derived.get("diversity"), dict) else {}
    baseline = derived.get("baseline") if isinstance(derived.get("baseline"), dict) else {}
    quality_blocks = derived.get("quality_blocks") if isinstance(derived.get("quality_blocks"), dict) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []

    lines: list[str] = []
    lines.append("# Chat Recommend Experiment Eval Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- metrics_source: {report.get('source', {}).get('metrics')}")
    if report.get("source", {}).get("session_state"):
        lines.append(f"- session_state_source: {report.get('source', {}).get('session_state')}")
    lines.append("")
    lines.append("## Diversity Variant")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| assigned | {diversity.get('assigned', 0):.0f} |")
    lines.append(f"| served | {diversity.get('served', 0):.0f} |")
    lines.append(f"| blocked | {diversity.get('blocked', 0):.0f} |")
    lines.append(f"| observed(served+blocked) | {diversity.get('observed', 0):.0f} |")
    lines.append(
        f"| block_rate ({diversity.get('block_rate_source', 'unknown')}) | {diversity.get('block_rate', 0.0):.4f} |"
    )
    lines.append("")
    lines.append("## Baseline Variant")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| assigned | {baseline.get('assigned', 0):.0f} |")
    lines.append(f"| served | {baseline.get('served', 0):.0f} |")
    lines.append(f"| blocked | {baseline.get('blocked', 0):.0f} |")
    lines.append("")
    lines.append("## Quality Blocks")
    lines.append("")
    if quality_blocks:
        for reason, value in sorted(quality_blocks.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {reason}: {value:.0f}")
    else:
        lines.append("- (none)")
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
    parser = argparse.ArgumentParser(description="Evaluate chat recommendation experiment metrics and gate quality.")
    parser.add_argument("--metrics-url", default="http://localhost:8001/metrics")
    parser.add_argument("--metrics-json", default="")
    parser.add_argument("--session-state-url", default="http://localhost:8001/internal/chat/session/state")
    parser.add_argument("--session-state-json", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_recommend_eval")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--max-block-rate", type=float, default=0.4)
    parser.add_argument("--max-auto-disable-total", type=float, default=0.0)
    parser.add_argument("--require-min-samples", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-block-rate-increase", type=float, default=0.05)
    parser.add_argument("--max-auto-disable-increase", type=float, default=0.0)
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
    derived = collect_recommend_metrics(metrics_snapshot)

    session_snapshot: dict[str, Any] | None = None
    session_source: str | None = None
    if args.session_state_json:
        payload = load_json(Path(args.session_state_json))
        session_value = payload.get("session")
        if isinstance(session_value, dict):
            session_snapshot = session_value
        session_source = str(Path(args.session_state_json))
    elif args.session_id:
        params = urllib.parse.urlencode({"session_id": args.session_id})
        url = f"{args.session_state_url}?{params}"
        payload = fetch_json(url, args.timeout)
        session_value = payload.get("session")
        if isinstance(session_value, dict):
            session_snapshot = session_value
        session_source = url

    session_auto_disabled = False
    if isinstance(session_snapshot, dict):
        recommend_exp = session_snapshot.get("recommend_experiment")
        if isinstance(recommend_exp, dict):
            session_auto_disabled = bool(recommend_exp.get("auto_disabled"))

    failures = evaluate_gate(
        derived,
        min_samples=max(1, args.min_samples),
        max_block_rate=max(0.0, min(1.0, args.max_block_rate)),
        max_auto_disable_total=max(0.0, args.max_auto_disable_total),
        require_min_samples=bool(args.require_min_samples),
        session_auto_disabled=session_auto_disabled,
    )

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            derived,
            max_block_rate_increase=max(0.0, min(1.0, args.max_block_rate_increase)),
            max_auto_disable_increase=max(0.0, args.max_auto_disable_increase),
        )

    passed = not failures and not baseline_failures

    report = {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "metrics": metrics_source,
            "session_state": session_source,
            "session_id": args.session_id or None,
            "baseline_report": args.baseline_report or None,
        },
        "thresholds": {
            "min_samples": max(1, args.min_samples),
            "max_block_rate": max(0.0, min(1.0, args.max_block_rate)),
            "max_auto_disable_total": max(0.0, args.max_auto_disable_total),
            "require_min_samples": bool(args.require_min_samples),
            "max_block_rate_increase": max(0.0, min(1.0, args.max_block_rate_increase)),
            "max_auto_disable_increase": max(0.0, args.max_auto_disable_increase),
        },
        "derived": derived,
        "session": session_snapshot,
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
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2)
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"[OK] report -> {json_path}")
    print(f"[OK] report -> {md_path}")

    if args.write_baseline:
        baseline_path = Path(args.write_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with baseline_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=True, indent=2)
        print(f"[OK] wrote baseline -> {baseline_path}")

    if not passed:
        print("[FAIL] recommendation quality gate failed:")
        for item in failures:
            print(f"  - {item}")
        for item in baseline_failures:
            print(f"  - {item}")
        return 2 if args.gate else 0
    print("[OK] recommendation quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
