#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


COMMERCE_INTENT_TOKENS = (
    "ORDER",
    "SHIPPING",
    "REFUND",
    "RETURN",
    "PAYMENT",
    "CANCEL",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bootstrap_pythonpath() -> None:
    root = _project_root()
    query_service = root / "services" / "query-service"
    if str(query_service) not in sys.path:
        sys.path.insert(0, str(query_service))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def _normalize_intent(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_commerce_intent(intent: Any) -> bool:
    normalized = _normalize_intent(intent)
    if not normalized:
        return False
    return any(token in normalized for token in COMMERCE_INTENT_TOKENS)


def _extract_intent(run_payload: Mapping[str, Any]) -> str:
    checkpoints = run_payload.get("checkpoints") if isinstance(run_payload.get("checkpoints"), list) else []
    for checkpoint in reversed(checkpoints):
        if not isinstance(checkpoint, Mapping):
            continue
        state = checkpoint.get("state") if isinstance(checkpoint.get("state"), Mapping) else {}
        intent = _normalize_intent(state.get("intent"))
        if intent:
            return intent

    replay_payload = run_payload.get("replay_payload") if isinstance(run_payload.get("replay_payload"), Mapping) else {}
    policy_decision = replay_payload.get("policy_decision") if isinstance(replay_payload.get("policy_decision"), Mapping) else {}
    intent = _normalize_intent(policy_decision.get("intent"))
    if intent:
        return intent
    return ""


def load_recent_runs(replay_dir: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    runs_dir = replay_dir / "runs"
    if not runs_dir.exists():
        return []

    rows: list[dict[str, Any]] = []
    for path in runs_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, Mapping):
            continue
        response = payload.get("response") if isinstance(payload.get("response"), Mapping) else {}
        rows.append(
            {
                "run_id": str(payload.get("run_id") or path.stem),
                "updated_at": _safe_int(payload.get("updated_at"), int(path.stat().st_mtime)),
                "intent": _extract_intent(payload),
                "status": str(response.get("status") or ""),
                "reason_code": str(response.get("reason_code") or ""),
                "next_action": str(response.get("next_action") or ""),
            }
        )
    rows.sort(key=lambda item: int(item.get("updated_at") or 0))
    return rows[-max(1, int(limit)) :]


def build_completion_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    run_total = len(rows)
    insufficient_total = sum(1 for row in rows if str(row.get("status") or "").lower() == "insufficient_evidence")
    commerce_rows = [row for row in rows if _is_commerce_intent(row.get("intent"))]

    commerce_total = len(commerce_rows)
    commerce_completed = 0
    by_intent: dict[str, dict[str, int | float]] = {}

    for row in commerce_rows:
        intent = _normalize_intent(row.get("intent")) or "UNKNOWN"
        status = str(row.get("status") or "").lower()
        next_action = str(row.get("next_action") or "").strip().upper()
        completed = status == "ok" and next_action in {"", "NONE"}
        if completed:
            commerce_completed += 1
        stats = by_intent.get(intent)
        if stats is None:
            stats = {"total": 0, "completed": 0, "completion_rate": 0.0}
            by_intent[intent] = stats
        stats["total"] = int(stats["total"]) + 1
        if completed:
            stats["completed"] = int(stats["completed"]) + 1
        total = int(stats["total"])
        stats["completion_rate"] = 0.0 if total == 0 else float(stats["completed"]) / float(total)

    insufficient_ratio = 0.0 if run_total == 0 else float(insufficient_total) / float(run_total)
    completion_rate = 0.0 if commerce_total == 0 else float(commerce_completed) / float(commerce_total)
    return {
        "run_total": run_total,
        "insufficient_evidence_total": insufficient_total,
        "insufficient_evidence_ratio": insufficient_ratio,
        "commerce_total": commerce_total,
        "commerce_completed_total": commerce_completed,
        "commerce_unresolved_total": max(0, commerce_total - commerce_completed),
        "commerce_completion_rate": completion_rate,
        "by_intent": by_intent,
        "samples": [dict(row) for row in rows[-20:]],
    }


def completion_summary_from_launch_metrics(payload: Mapping[str, Any]) -> dict[str, Any]:
    by_intent = payload.get("by_intent") if isinstance(payload.get("by_intent"), Mapping) else {}
    by_domain = payload.get("by_domain") if isinstance(payload.get("by_domain"), Mapping) else {}
    commerce = by_domain.get("commerce") if isinstance(by_domain.get("commerce"), Mapping) else {}
    return {
        "run_total": _safe_int(payload.get("total"), 0),
        "insufficient_evidence_total": _safe_int(payload.get("insufficient_total"), 0),
        "insufficient_evidence_ratio": _safe_float(payload.get("insufficient_ratio"), 0.0),
        "commerce_total": _safe_int(commerce.get("total"), 0),
        "commerce_completed_total": _safe_int(commerce.get("completed_total"), 0),
        "commerce_unresolved_total": max(
            0,
            _safe_int(commerce.get("total"), 0) - _safe_int(commerce.get("completed_total"), 0),
        ),
        "commerce_completion_rate": _safe_float(commerce.get("completion_rate"), 0.0),
        "by_intent": dict(by_intent),
        "by_domain": dict(by_domain),
        "samples": [],
    }


def build_release_profile(
    *,
    model_version: str | None,
    prompt_version: str | None,
    policy_version: str | None,
) -> dict[str, str]:
    model = str(model_version or "").strip() or str(os.getenv("QS_LLM_MODEL", "")).strip() or "unknown"
    prompt = str(prompt_version or "").strip() or str(os.getenv("QS_CHAT_PROMPT_VERSION", "")).strip() or "unknown"
    policy = str(policy_version or "").strip() or str(os.getenv("QS_CHAT_POLICY_VERSION", "")).strip() or "unknown"
    raw = json.dumps(
        {
            "model_version": model,
            "prompt_version": prompt,
            "policy_version": policy,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    signature = hashlib.sha256(raw).hexdigest()[:16]
    return {
        "model_version": model,
        "prompt_version": prompt,
        "policy_version": policy,
        "release_signature": signature,
    }


def evaluate_gate(
    *,
    parity_payload: Mapping[str, Any],
    canary_decision: Mapping[str, Any],
    budget_decision: Mapping[str, Any],
    reason_summary: Mapping[str, Any],
    legacy_summary: Mapping[str, Any],
    completion_summary: Mapping[str, Any],
    min_reason_window: int,
    min_legacy_window: int,
    min_run_window: int,
    min_commerce_samples: int,
    max_mismatch_ratio: float,
    max_blocker_ratio: float,
    max_reason_invalid_ratio: float,
    max_reason_unknown_ratio: float,
    max_legacy_ratio: float,
    max_legacy_count: int,
    min_commerce_completion_rate: float,
    max_insufficient_evidence_ratio: float,
) -> list[str]:
    failures: list[str] = []

    mismatch_ratio = _safe_float(parity_payload.get("mismatch_ratio"), 0.0)
    blocker_ratio = _safe_float(parity_payload.get("blocker_ratio"), 0.0)
    if not bool(canary_decision.get("passed")):
        failures.append(f"canary gate failed: reason={canary_decision.get('reason')}")
    if mismatch_ratio > max(0.0, float(max_mismatch_ratio)):
        failures.append(f"mismatch ratio exceeded: {mismatch_ratio:.4f} > {float(max_mismatch_ratio):.4f}")
    if blocker_ratio > max(0.0, float(max_blocker_ratio)):
        failures.append(f"blocker ratio exceeded: {blocker_ratio:.4f} > {float(max_blocker_ratio):.4f}")

    if not bool(budget_decision.get("passed")):
        budget_failures = budget_decision.get("failures") if isinstance(budget_decision.get("failures"), list) else []
        if budget_failures:
            for failure in budget_failures:
                failures.append(f"budget gate failed: {failure}")
        else:
            failures.append("budget gate failed: unknown")

    reason_window = _safe_int(reason_summary.get("window_size"), 0)
    reason_invalid_ratio = _safe_float(reason_summary.get("invalid_ratio"), 0.0)
    reason_unknown_ratio = _safe_float(reason_summary.get("unknown_ratio"), 0.0)
    if reason_window < max(0, int(min_reason_window)):
        failures.append(f"insufficient reason samples: window_size={reason_window} < min_reason_window={min_reason_window}")
    if reason_invalid_ratio > max(0.0, float(max_reason_invalid_ratio)):
        failures.append(
            f"reason invalid ratio exceeded: {reason_invalid_ratio:.4f} > {float(max_reason_invalid_ratio):.4f}"
        )
    if reason_unknown_ratio > max(0.0, float(max_reason_unknown_ratio)):
        failures.append(
            f"reason unknown ratio exceeded: {reason_unknown_ratio:.4f} > {float(max_reason_unknown_ratio):.4f}"
        )

    legacy_window = _safe_int(legacy_summary.get("window_size"), 0)
    legacy_count = _safe_int(legacy_summary.get("legacy_count"), 0)
    legacy_ratio = _safe_float(legacy_summary.get("legacy_ratio"), 0.0)
    if legacy_window < max(0, int(min_legacy_window)):
        failures.append(f"insufficient legacy samples: window_size={legacy_window} < min_legacy_window={min_legacy_window}")
    if legacy_count > max(0, int(max_legacy_count)):
        failures.append(f"legacy count exceeded: {legacy_count} > {int(max_legacy_count)}")
    if legacy_ratio > max(0.0, float(max_legacy_ratio)):
        failures.append(f"legacy ratio exceeded: {legacy_ratio:.4f} > {float(max_legacy_ratio):.4f}")

    run_total = _safe_int(completion_summary.get("run_total"), 0)
    commerce_total = _safe_int(completion_summary.get("commerce_total"), 0)
    completion_rate = _safe_float(completion_summary.get("commerce_completion_rate"), 0.0)
    insufficient_ratio = _safe_float(completion_summary.get("insufficient_evidence_ratio"), 0.0)
    if run_total < max(0, int(min_run_window)):
        failures.append(f"insufficient replay samples: run_total={run_total} < min_run_window={min_run_window}")
    if commerce_total < max(0, int(min_commerce_samples)):
        failures.append(
            f"insufficient commerce samples: commerce_total={commerce_total} < min_commerce_samples={min_commerce_samples}"
        )
    if commerce_total > 0 and completion_rate < max(0.0, float(min_commerce_completion_rate)):
        failures.append(
            f"commerce completion rate below threshold: {completion_rate:.4f} < {float(min_commerce_completion_rate):.4f}"
        )
    if run_total > 0 and insufficient_ratio > max(0.0, float(max_insufficient_evidence_ratio)):
        failures.append(
            f"insufficient_evidence ratio exceeded: {insufficient_ratio:.4f} > {float(max_insufficient_evidence_ratio):.4f}"
        )

    return failures


def compare_with_baseline(
    baseline_report: Mapping[str, Any],
    current_report: Mapping[str, Any],
    *,
    max_mismatch_ratio_increase: float,
    max_blocker_ratio_increase: float,
    max_reason_invalid_ratio_increase: float,
    max_reason_unknown_ratio_increase: float,
    max_legacy_ratio_increase: float,
    max_insufficient_evidence_ratio_increase: float,
    max_completion_rate_drop: float,
) -> list[str]:
    failures: list[str] = []
    base_derived = baseline_report.get("derived") if isinstance(baseline_report.get("derived"), Mapping) else {}
    cur_derived = current_report.get("derived") if isinstance(current_report.get("derived"), Mapping) else {}

    base_parity = base_derived.get("parity") if isinstance(base_derived.get("parity"), Mapping) else {}
    cur_parity = cur_derived.get("parity") if isinstance(cur_derived.get("parity"), Mapping) else {}
    base_reason = base_derived.get("reason") if isinstance(base_derived.get("reason"), Mapping) else {}
    cur_reason = cur_derived.get("reason") if isinstance(cur_derived.get("reason"), Mapping) else {}
    base_legacy = base_derived.get("legacy") if isinstance(base_derived.get("legacy"), Mapping) else {}
    cur_legacy = cur_derived.get("legacy") if isinstance(cur_derived.get("legacy"), Mapping) else {}
    base_completion = base_derived.get("completion") if isinstance(base_derived.get("completion"), Mapping) else {}
    cur_completion = cur_derived.get("completion") if isinstance(cur_derived.get("completion"), Mapping) else {}

    mismatch_increase = _safe_float(cur_parity.get("mismatch_ratio"), 0.0) - _safe_float(base_parity.get("mismatch_ratio"), 0.0)
    if mismatch_increase > max(0.0, float(max_mismatch_ratio_increase)):
        failures.append(
            f"mismatch ratio regression: baseline={_safe_float(base_parity.get('mismatch_ratio'), 0.0):.4f}, current={_safe_float(cur_parity.get('mismatch_ratio'), 0.0):.4f}, allowed_increase={float(max_mismatch_ratio_increase):.4f}"
        )

    blocker_increase = _safe_float(cur_parity.get("blocker_ratio"), 0.0) - _safe_float(base_parity.get("blocker_ratio"), 0.0)
    if blocker_increase > max(0.0, float(max_blocker_ratio_increase)):
        failures.append(
            f"blocker ratio regression: baseline={_safe_float(base_parity.get('blocker_ratio'), 0.0):.4f}, current={_safe_float(cur_parity.get('blocker_ratio'), 0.0):.4f}, allowed_increase={float(max_blocker_ratio_increase):.4f}"
        )

    invalid_increase = _safe_float(cur_reason.get("invalid_ratio"), 0.0) - _safe_float(base_reason.get("invalid_ratio"), 0.0)
    if invalid_increase > max(0.0, float(max_reason_invalid_ratio_increase)):
        failures.append(
            f"reason invalid ratio regression: baseline={_safe_float(base_reason.get('invalid_ratio'), 0.0):.4f}, current={_safe_float(cur_reason.get('invalid_ratio'), 0.0):.4f}, allowed_increase={float(max_reason_invalid_ratio_increase):.4f}"
        )

    unknown_increase = _safe_float(cur_reason.get("unknown_ratio"), 0.0) - _safe_float(base_reason.get("unknown_ratio"), 0.0)
    if unknown_increase > max(0.0, float(max_reason_unknown_ratio_increase)):
        failures.append(
            f"reason unknown ratio regression: baseline={_safe_float(base_reason.get('unknown_ratio'), 0.0):.4f}, current={_safe_float(cur_reason.get('unknown_ratio'), 0.0):.4f}, allowed_increase={float(max_reason_unknown_ratio_increase):.4f}"
        )

    legacy_increase = _safe_float(cur_legacy.get("legacy_ratio"), 0.0) - _safe_float(base_legacy.get("legacy_ratio"), 0.0)
    if legacy_increase > max(0.0, float(max_legacy_ratio_increase)):
        failures.append(
            f"legacy ratio regression: baseline={_safe_float(base_legacy.get('legacy_ratio'), 0.0):.4f}, current={_safe_float(cur_legacy.get('legacy_ratio'), 0.0):.4f}, allowed_increase={float(max_legacy_ratio_increase):.4f}"
        )

    insufficient_increase = _safe_float(cur_completion.get("insufficient_evidence_ratio"), 0.0) - _safe_float(base_completion.get("insufficient_evidence_ratio"), 0.0)
    if insufficient_increase > max(0.0, float(max_insufficient_evidence_ratio_increase)):
        failures.append(
            f"insufficient_evidence ratio regression: baseline={_safe_float(base_completion.get('insufficient_evidence_ratio'), 0.0):.4f}, current={_safe_float(cur_completion.get('insufficient_evidence_ratio'), 0.0):.4f}, allowed_increase={float(max_insufficient_evidence_ratio_increase):.4f}"
        )

    completion_drop = _safe_float(base_completion.get("commerce_completion_rate"), 0.0) - _safe_float(cur_completion.get("commerce_completion_rate"), 0.0)
    if completion_drop > max(0.0, float(max_completion_rate_drop)):
        failures.append(
            f"commerce completion rate regression: baseline={_safe_float(base_completion.get('commerce_completion_rate'), 0.0):.4f}, current={_safe_float(cur_completion.get('commerce_completion_rate'), 0.0):.4f}, allowed_drop={float(max_completion_rate_drop):.4f}"
        )

    return failures


def render_markdown(report: Mapping[str, Any]) -> str:
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    derived = report.get("derived") if isinstance(report.get("derived"), Mapping) else {}
    completion = derived.get("completion") if isinstance(derived.get("completion"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat Production Launch Gate Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    release = report.get("release_profile") if isinstance(report.get("release_profile"), Mapping) else {}
    lines.append(
        f"- release: model={release.get('model_version')} prompt={release.get('prompt_version')} policy={release.get('policy_version')} signature={release.get('release_signature')}"
    )
    lines.append(f"- pass: {str(bool(gate.get('pass'))).lower()}")
    lines.append(f"- failure_count: {len(gate.get('failures') or [])}")
    lines.append("")
    lines.append("## Key Metrics")
    lines.append("")
    lines.append(
        f"- commerce_completion_rate: {float(completion.get('commerce_completion_rate') or 0.0):.4f} ({int(completion.get('commerce_completed_total') or 0)}/{int(completion.get('commerce_total') or 0)})"
    )
    lines.append(f"- insufficient_evidence_ratio: {float(completion.get('insufficient_evidence_ratio') or 0.0):.4f}")
    lines.append("")
    lines.append("## Gate Failures")
    lines.append("")
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    if failures:
        for item in failures:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate production launch readiness gate for chat.")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_production_launch_gate")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--replay-dir", default="var/chat_graph/replay")
    parser.add_argument("--completion-source", choices=["auto", "launch_metrics", "replay"], default="auto")
    parser.add_argument("--parity-limit", type=int, default=200)
    parser.add_argument("--perf-limit", type=int, default=500)
    parser.add_argument("--reason-limit", type=int, default=500)
    parser.add_argument("--legacy-limit", type=int, default=500)
    parser.add_argument("--run-limit", type=int, default=300)
    parser.add_argument("--min-reason-window", type=int, default=20)
    parser.add_argument("--min-legacy-window", type=int, default=20)
    parser.add_argument("--min-run-window", type=int, default=20)
    parser.add_argument("--min-commerce-samples", type=int, default=10)
    parser.add_argument("--max-mismatch-ratio", type=float, default=0.10)
    parser.add_argument("--max-blocker-ratio", type=float, default=0.02)
    parser.add_argument("--max-reason-invalid-ratio", type=float, default=0.0)
    parser.add_argument("--max-reason-unknown-ratio", type=float, default=0.05)
    parser.add_argument("--max-legacy-ratio", type=float, default=0.0)
    parser.add_argument("--max-legacy-count", type=int, default=0)
    parser.add_argument("--min-commerce-completion-rate", type=float, default=0.90)
    parser.add_argument("--max-insufficient-evidence-ratio", type=float, default=0.30)
    parser.add_argument("--model-version", default="")
    parser.add_argument("--prompt-version", default="")
    parser.add_argument("--policy-version", default="")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-mismatch-ratio-increase", type=float, default=0.01)
    parser.add_argument("--max-blocker-ratio-increase", type=float, default=0.005)
    parser.add_argument("--max-reason-invalid-ratio-increase", type=float, default=0.0)
    parser.add_argument("--max-reason-unknown-ratio-increase", type=float, default=0.01)
    parser.add_argument("--max-legacy-ratio-increase", type=float, default=0.0)
    parser.add_argument("--max-insufficient-evidence-ratio-increase", type=float, default=0.05)
    parser.add_argument("--max-completion-rate-drop", type=float, default=0.03)
    parser.add_argument("--write-baseline", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _bootstrap_pythonpath()

    from app.core.chat_graph.canary_controller import evaluate_canary_gate
    from app.core.chat_graph.feature_router import build_legacy_mode_summary
    from app.core.chat_graph.launch_metrics import load_launch_metrics_summary
    from app.core.chat_graph.perf_budget import build_perf_summary, evaluate_budget_gate
    from app.core.chat_graph.reason_taxonomy import build_reason_code_summary
    from app.core.chat_graph.shadow_comparator import build_gate_payload

    parity_payload = build_gate_payload(limit=max(1, int(args.parity_limit)))
    canary = evaluate_canary_gate(parity_payload)
    perf_summary = build_perf_summary(limit=max(1, int(args.perf_limit)))
    budget = evaluate_budget_gate(perf_summary)
    reason_summary = build_reason_code_summary(limit=max(1, int(args.reason_limit)))
    legacy_summary = build_legacy_mode_summary(limit=max(1, int(args.legacy_limit)))

    completion_source_used = str(args.completion_source)
    launch_completion_summary = completion_summary_from_launch_metrics(load_launch_metrics_summary())
    if args.completion_source == "launch_metrics":
        completion_summary = launch_completion_summary
    elif args.completion_source == "replay":
        run_rows = load_recent_runs(Path(args.replay_dir), limit=max(1, int(args.run_limit)))
        completion_summary = build_completion_summary(run_rows)
    else:
        if _safe_int(launch_completion_summary.get("run_total"), 0) > 0:
            completion_summary = launch_completion_summary
            completion_source_used = "launch_metrics"
        else:
            run_rows = load_recent_runs(Path(args.replay_dir), limit=max(1, int(args.run_limit)))
            completion_summary = build_completion_summary(run_rows)
            completion_source_used = "replay"

    failures = evaluate_gate(
        parity_payload=parity_payload,
        canary_decision={
            "passed": canary.passed,
            "reason": canary.reason,
            "gate_status": canary.gate_status,
            "mismatch_ratio": canary.mismatch_ratio,
            "blocker_ratio": canary.blocker_ratio,
        },
        budget_decision={"passed": budget.passed, "failures": budget.failures},
        reason_summary=reason_summary,
        legacy_summary=legacy_summary,
        completion_summary=completion_summary,
        min_reason_window=max(0, int(args.min_reason_window)),
        min_legacy_window=max(0, int(args.min_legacy_window)),
        min_run_window=max(0, int(args.min_run_window)),
        min_commerce_samples=max(0, int(args.min_commerce_samples)),
        max_mismatch_ratio=max(0.0, float(args.max_mismatch_ratio)),
        max_blocker_ratio=max(0.0, float(args.max_blocker_ratio)),
        max_reason_invalid_ratio=max(0.0, float(args.max_reason_invalid_ratio)),
        max_reason_unknown_ratio=max(0.0, float(args.max_reason_unknown_ratio)),
        max_legacy_ratio=max(0.0, float(args.max_legacy_ratio)),
        max_legacy_count=max(0, int(args.max_legacy_count)),
        min_commerce_completion_rate=max(0.0, float(args.min_commerce_completion_rate)),
        max_insufficient_evidence_ratio=max(0.0, float(args.max_insufficient_evidence_ratio)),
    )
    release_profile = build_release_profile(
        model_version=args.model_version,
        prompt_version=args.prompt_version,
        policy_version=args.policy_version,
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_profile": release_profile,
        "source": {
            "replay_dir": str(args.replay_dir),
            "completion_source": str(args.completion_source),
            "completion_source_used": completion_source_used,
            "baseline_report": str(args.baseline_report) if args.baseline_report else None,
            "limits": {
                "parity_limit": int(args.parity_limit),
                "perf_limit": int(args.perf_limit),
                "reason_limit": int(args.reason_limit),
                "legacy_limit": int(args.legacy_limit),
                "run_limit": int(args.run_limit),
            },
        },
        "derived": {
            "parity": parity_payload,
            "canary": {
                "passed": canary.passed,
                "gate_status": canary.gate_status,
                "reason": canary.reason,
                "mismatch_ratio": canary.mismatch_ratio,
                "blocker_ratio": canary.blocker_ratio,
            },
            "perf": perf_summary,
            "budget": {"passed": budget.passed, "failures": budget.failures},
            "reason": reason_summary,
            "legacy": legacy_summary,
            "completion": completion_summary,
        },
        "gate": {
            "enabled": bool(args.gate),
            "pass": len(failures) == 0,
            "failures": failures,
            "thresholds": {
                "min_reason_window": int(args.min_reason_window),
                "min_legacy_window": int(args.min_legacy_window),
                "min_run_window": int(args.min_run_window),
                "min_commerce_samples": int(args.min_commerce_samples),
                "max_mismatch_ratio": float(args.max_mismatch_ratio),
                "max_blocker_ratio": float(args.max_blocker_ratio),
                "max_reason_invalid_ratio": float(args.max_reason_invalid_ratio),
                "max_reason_unknown_ratio": float(args.max_reason_unknown_ratio),
                "max_legacy_ratio": float(args.max_legacy_ratio),
                "max_legacy_count": int(args.max_legacy_count),
                "min_commerce_completion_rate": float(args.min_commerce_completion_rate),
                "max_insufficient_evidence_ratio": float(args.max_insufficient_evidence_ratio),
            },
        },
    }

    baseline_failures: list[str] = []
    if args.baseline_report:
        baseline_report = load_json(Path(args.baseline_report))
        baseline_failures = compare_with_baseline(
            baseline_report,
            report,
            max_mismatch_ratio_increase=max(0.0, float(args.max_mismatch_ratio_increase)),
            max_blocker_ratio_increase=max(0.0, float(args.max_blocker_ratio_increase)),
            max_reason_invalid_ratio_increase=max(0.0, float(args.max_reason_invalid_ratio_increase)),
            max_reason_unknown_ratio_increase=max(0.0, float(args.max_reason_unknown_ratio_increase)),
            max_legacy_ratio_increase=max(0.0, float(args.max_legacy_ratio_increase)),
            max_insufficient_evidence_ratio_increase=max(0.0, float(args.max_insufficient_evidence_ratio_increase)),
            max_completion_rate_drop=max(0.0, float(args.max_completion_rate_drop)),
        )

    gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
    gate["baseline_failures"] = baseline_failures
    gate["pass"] = len(failures) == 0 and len(baseline_failures) == 0
    gate["thresholds"] = dict(gate.get("thresholds") or {})
    gate["thresholds"]["max_mismatch_ratio_increase"] = float(args.max_mismatch_ratio_increase)
    gate["thresholds"]["max_blocker_ratio_increase"] = float(args.max_blocker_ratio_increase)
    gate["thresholds"]["max_reason_invalid_ratio_increase"] = float(args.max_reason_invalid_ratio_increase)
    gate["thresholds"]["max_reason_unknown_ratio_increase"] = float(args.max_reason_unknown_ratio_increase)
    gate["thresholds"]["max_legacy_ratio_increase"] = float(args.max_legacy_ratio_increase)
    gate["thresholds"]["max_insufficient_evidence_ratio_increase"] = float(args.max_insufficient_evidence_ratio_increase)
    gate["thresholds"]["max_completion_rate_drop"] = float(args.max_completion_rate_drop)
    report["gate"] = gate

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"gate_pass={str(report['gate']['pass']).lower()}")

    if args.gate and not bool(report["gate"]["pass"]):
        for item in failures:
            print(f"[gate-failure] {item}")
        for item in baseline_failures:
            print(f"[baseline-failure] {item}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
