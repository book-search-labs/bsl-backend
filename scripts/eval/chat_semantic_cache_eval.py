import argparse
import json
import urllib.parse
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


def collect_semantic_cache_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    quality_total = 0.0
    quality_error = 0.0
    hit_total = 0.0
    store_total = 0.0
    block_total = 0.0
    auto_disable_total = 0.0
    blocks_by_reason: dict[str, float] = {}
    quality_by_reason: dict[str, float] = {}
    policy_topic_hits_by_topic: dict[str, float] = {}
    policy_topic_miss_by_reason: dict[str, float] = {}
    policy_topic_hit_total = 0.0
    policy_topic_miss_total = 0.0

    for key, value in (snapshot or {}).items():
        name, labels = parse_metric_key(str(key))
        metric_value = _to_float(value)
        if name == "chat_semantic_cache_quality_total":
            result = labels.get("result", "unknown")
            reason = labels.get("reason", "unknown")
            quality_total += metric_value
            if result == "error":
                quality_error += metric_value
            quality_by_reason[reason] = quality_by_reason.get(reason, 0.0) + metric_value
            continue
        if name == "chat_semantic_cache_hit_total":
            hit_total += metric_value
            continue
        if name == "chat_semantic_cache_store_total":
            store_total += metric_value
            continue
        if name == "chat_semantic_cache_block_total":
            reason = labels.get("reason", "unknown")
            block_total += metric_value
            blocks_by_reason[reason] = blocks_by_reason.get(reason, 0.0) + metric_value
            continue
        if name == "chat_semantic_cache_auto_disable_total":
            auto_disable_total += metric_value
            continue
        if name == "chat_policy_topic_cache_hit_total":
            topic = labels.get("topic", "unknown")
            policy_topic_hit_total += metric_value
            policy_topic_hits_by_topic[topic] = policy_topic_hits_by_topic.get(topic, 0.0) + metric_value
            continue
        if name == "chat_policy_topic_miss_total":
            reason = labels.get("reason", "unknown")
            policy_topic_miss_total += metric_value
            policy_topic_miss_by_reason[reason] = policy_topic_miss_by_reason.get(reason, 0.0) + metric_value
            continue

    error_rate = (quality_error / quality_total) if quality_total > 0 else 0.0
    return {
        "quality_total": quality_total,
        "quality_error": quality_error,
        "quality_error_rate": error_rate,
        "hit_total": hit_total,
        "store_total": store_total,
        "block_total": block_total,
        "auto_disable_total": auto_disable_total,
        "blocks_by_reason": blocks_by_reason,
        "quality_by_reason": quality_by_reason,
        "policy_topic_hit_total": policy_topic_hit_total,
        "policy_topic_miss_total": policy_topic_miss_total,
        "policy_topic_hits_by_topic": policy_topic_hits_by_topic,
        "policy_topic_miss_by_reason": policy_topic_miss_by_reason,
    }


def evaluate_gate(
    derived: dict[str, Any],
    *,
    min_quality_samples: int,
    max_error_rate: float,
    max_auto_disable_total: float,
    require_min_samples: bool,
    session_auto_disabled: bool,
) -> list[str]:
    failures: list[str] = []
    quality_total = _to_float(derived.get("quality_total", 0.0))
    error_rate = _to_float(derived.get("quality_error_rate", 0.0))
    auto_disable_total = _to_float(derived.get("auto_disable_total", 0.0))

    if require_min_samples and quality_total < float(max(1, min_quality_samples)):
        failures.append(
            "insufficient semantic cache quality samples: "
            f"quality_total={quality_total:.0f} < min_quality_samples={min_quality_samples}"
        )
    if quality_total > 0 and error_rate > max_error_rate:
        failures.append(f"semantic cache error rate too high: error_rate={error_rate:.4f} > {max_error_rate:.4f}")
    if auto_disable_total > max_auto_disable_total:
        failures.append(
            "semantic cache auto-disable events exceed limit: "
            f"auto_disable_total={auto_disable_total:.0f} > {max_auto_disable_total:.0f}"
        )
    if session_auto_disabled:
        failures.append("session snapshot indicates semantic_cache auto_disabled=true")
    return failures


def compare_with_baseline(
    baseline_report: dict[str, Any],
    current_derived: dict[str, Any],
    *,
    max_error_rate_increase: float,
    max_auto_disable_increase: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), dict) else {}
    base_error_rate = _to_float(base_derived.get("quality_error_rate", 0.0))
    curr_error_rate = _to_float(current_derived.get("quality_error_rate", 0.0))
    if curr_error_rate > base_error_rate + max_error_rate_increase:
        failures.append(
            "semantic cache error rate regression: "
            f"baseline={base_error_rate:.4f}, current={curr_error_rate:.4f}, "
            f"allowed_increase={max_error_rate_increase:.4f}"
        )

    base_auto = _to_float(base_derived.get("auto_disable_total", 0.0))
    curr_auto = _to_float(current_derived.get("auto_disable_total", 0.0))
    if curr_auto > base_auto + max_auto_disable_increase:
        failures.append(
            "semantic cache auto-disable regression: "
            f"baseline={base_auto:.0f}, current={curr_auto:.0f}, "
            f"allowed_increase={max_auto_disable_increase:.0f}"
        )
    return failures


def render_markdown(report: dict[str, Any]) -> str:
    derived = report.get("derived") if isinstance(report.get("derived"), dict) else {}
    gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    baseline_failures = gate.get("baseline_failures") if isinstance(gate.get("baseline_failures"), list) else []
    blocks_by_reason = derived.get("blocks_by_reason") if isinstance(derived.get("blocks_by_reason"), dict) else {}
    quality_by_reason = derived.get("quality_by_reason") if isinstance(derived.get("quality_by_reason"), dict) else {}
    topic_hits = derived.get("policy_topic_hits_by_topic") if isinstance(derived.get("policy_topic_hits_by_topic"), dict) else {}
    topic_miss = derived.get("policy_topic_miss_by_reason") if isinstance(derived.get("policy_topic_miss_by_reason"), dict) else {}

    lines: list[str] = []
    lines.append("# Chat Semantic Cache Eval Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- metrics_source: {report.get('source', {}).get('metrics')}")
    if report.get("source", {}).get("session_state"):
        lines.append(f"- session_state_source: {report.get('source', {}).get('session_state')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| quality_total | {derived.get('quality_total', 0):.0f} |")
    lines.append(f"| quality_error | {derived.get('quality_error', 0):.0f} |")
    lines.append(f"| quality_error_rate | {derived.get('quality_error_rate', 0):.4f} |")
    lines.append(f"| hit_total | {derived.get('hit_total', 0):.0f} |")
    lines.append(f"| store_total | {derived.get('store_total', 0):.0f} |")
    lines.append(f"| block_total | {derived.get('block_total', 0):.0f} |")
    lines.append(f"| auto_disable_total | {derived.get('auto_disable_total', 0):.0f} |")
    lines.append(f"| policy_topic_hit_total | {derived.get('policy_topic_hit_total', 0):.0f} |")
    lines.append(f"| policy_topic_miss_total | {derived.get('policy_topic_miss_total', 0):.0f} |")
    lines.append("")
    lines.append("## Blocks By Reason")
    lines.append("")
    if blocks_by_reason:
        for reason, value in sorted(blocks_by_reason.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {reason}: {value:.0f}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Quality By Reason")
    lines.append("")
    if quality_by_reason:
        for reason, value in sorted(quality_by_reason.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {reason}: {value:.0f}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Policy Topic Hits")
    lines.append("")
    if topic_hits:
        for topic, value in sorted(topic_hits.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {topic}: {value:.0f}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Policy Topic Misses")
    lines.append("")
    if topic_miss:
        for reason, value in sorted(topic_miss.items(), key=lambda item: item[1], reverse=True):
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
    parser = argparse.ArgumentParser(description="Evaluate semantic cache safety metrics and gate quality.")
    parser.add_argument("--metrics-url", default="http://localhost:8001/metrics")
    parser.add_argument("--metrics-json", default="")
    parser.add_argument("--session-state-url", default="http://localhost:8001/internal/chat/session/state")
    parser.add_argument("--session-state-json", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_semantic_cache_eval")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-quality-samples", type=int, default=20)
    parser.add_argument("--max-error-rate", type=float, default=0.2)
    parser.add_argument("--max-auto-disable-total", type=float, default=0.0)
    parser.add_argument("--require-min-samples", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-error-rate-increase", type=float, default=0.05)
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

    derived = collect_semantic_cache_metrics(metrics_snapshot)

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
        semantic = session_snapshot.get("semantic_cache")
        if isinstance(semantic, dict):
            session_auto_disabled = bool(semantic.get("auto_disabled"))

    failures = evaluate_gate(
        derived,
        min_quality_samples=max(1, args.min_quality_samples),
        max_error_rate=max(0.0, min(1.0, args.max_error_rate)),
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
            max_error_rate_increase=max(0.0, min(1.0, args.max_error_rate_increase)),
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
            "min_quality_samples": max(1, args.min_quality_samples),
            "max_error_rate": max(0.0, min(1.0, args.max_error_rate)),
            "max_auto_disable_total": max(0.0, args.max_auto_disable_total),
            "require_min_samples": bool(args.require_min_samples),
            "max_error_rate_increase": max(0.0, min(1.0, args.max_error_rate_increase)),
            "max_auto_disable_increase": max(0.0, args.max_auto_disable_increase),
        },
        "derived": derived,
        "session": {
            "semantic_cache_auto_disabled": session_auto_disabled,
        },
        "gate": {
            "pass": passed,
            "failures": failures,
            "baseline_failures": baseline_failures,
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

    print(f"[chat_semantic_cache_eval] report(json): {json_path}")
    print(f"[chat_semantic_cache_eval] report(md): {md_path}")
    print(f"[chat_semantic_cache_eval] gate_pass={str(passed).lower()}")

    if args.gate and not passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
