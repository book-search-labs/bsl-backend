#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _python_bin() -> str:
    return sys.executable or "python3"


def _load_module(script_name: str):
    path = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def _parse_report_path(output: str) -> str:
    for line in str(output or "").splitlines():
        if line.startswith("report_json="):
            return line.split("=", 1)[1].strip()
    return ""


def run_launch_gate_subprocess(
    *,
    out_dir: str,
    replay_dir: str,
    completion_source: str,
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
    min_completion_rate: float,
    max_insufficient_ratio: float,
    model_version: str,
    prompt_version: str,
    policy_version: str,
    baseline_report: str,
    max_mismatch_ratio_increase: float,
    max_blocker_ratio_increase: float,
    max_reason_invalid_ratio_increase: float,
    max_reason_unknown_ratio_increase: float,
    max_legacy_ratio_increase: float,
    max_insufficient_ratio_increase: float,
    max_completion_rate_drop: float,
    triage_out: str,
    triage_max_samples: int,
) -> tuple[int, str, str]:
    script = _project_root() / "scripts" / "eval" / "chat_production_launch_gate.py"
    cmd = [
        _python_bin(),
        str(script),
        "--out",
        str(out_dir),
        "--replay-dir",
        str(replay_dir),
        "--completion-source",
        str(completion_source),
        "--min-reason-window",
        str(int(min_reason_window)),
        "--min-legacy-window",
        str(int(min_legacy_window)),
        "--min-run-window",
        str(int(min_run_window)),
        "--min-commerce-samples",
        str(int(min_commerce_samples)),
        "--max-mismatch-ratio",
        str(float(max_mismatch_ratio)),
        "--max-blocker-ratio",
        str(float(max_blocker_ratio)),
        "--max-reason-invalid-ratio",
        str(float(max_reason_invalid_ratio)),
        "--max-reason-unknown-ratio",
        str(float(max_reason_unknown_ratio)),
        "--max-legacy-ratio",
        str(float(max_legacy_ratio)),
        "--max-legacy-count",
        str(int(max_legacy_count)),
        "--min-commerce-completion-rate",
        str(float(min_completion_rate)),
        "--max-insufficient-evidence-ratio",
        str(float(max_insufficient_ratio)),
        "--model-version",
        str(model_version),
        "--prompt-version",
        str(prompt_version),
        "--policy-version",
        str(policy_version),
        "--max-mismatch-ratio-increase",
        str(float(max_mismatch_ratio_increase)),
        "--max-blocker-ratio-increase",
        str(float(max_blocker_ratio_increase)),
        "--max-reason-invalid-ratio-increase",
        str(float(max_reason_invalid_ratio_increase)),
        "--max-reason-unknown-ratio-increase",
        str(float(max_reason_unknown_ratio_increase)),
        "--max-legacy-ratio-increase",
        str(float(max_legacy_ratio_increase)),
        "--max-insufficient-evidence-ratio-increase",
        str(float(max_insufficient_ratio_increase)),
        "--max-completion-rate-drop",
        str(float(max_completion_rate_drop)),
        "--triage-out",
        str(triage_out),
        "--triage-max-samples",
        str(int(triage_max_samples)),
        "--gate",
    ]
    if str(baseline_report).strip():
        cmd.extend(["--baseline-report", str(baseline_report)])
    proc = subprocess.run(
        cmd,
        cwd=str(_project_root()),
        capture_output=True,
        text=True,
        check=False,
    )
    report_path = _parse_report_path(proc.stdout)
    return proc.returncode, proc.stdout, report_path


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {path}")
    return payload


def render_markdown(report: Mapping[str, Any]) -> str:
    release = report.get("release_profile") if isinstance(report.get("release_profile"), Mapping) else {}
    launch = report.get("launch_gate") if isinstance(report.get("launch_gate"), Mapping) else {}
    decision = report.get("release_train") if isinstance(report.get("release_train"), Mapping) else {}
    release_decision = decision.get("decision") if isinstance(decision.get("decision"), Mapping) else {}
    lines: list[str] = []
    lines.append("# Chat LiveOps Cycle Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- release_signature: {release.get('release_signature')}")
    lines.append(f"- launch_gate_pass: {str(bool(launch.get('pass'))).lower()}")
    lines.append(f"- release_action: {release_decision.get('action')}")
    lines.append(f"- release_reason: {release_decision.get('reason')}")
    lines.append(f"- next_stage: {release_decision.get('next_stage')}")
    lines.append("")
    failures = report.get("failures") if isinstance(report.get("failures"), list) else []
    lines.append("## Failures")
    lines.append("")
    if failures:
        for item in failures:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run launch gate + release-train decision as one LiveOps cycle.")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--prefix", default="chat_liveops_cycle")
    parser.add_argument("--launch-gate-report", default="")
    parser.add_argument("--reports-dir", default="data/eval/reports")
    parser.add_argument("--launch-report-prefix", default="chat_production_launch_gate")
    parser.add_argument("--replay-dir", default="var/chat_graph/replay")
    parser.add_argument("--completion-source", choices=["auto", "launch_metrics", "replay"], default="auto")
    parser.add_argument("--current-stage", type=int, default=10)
    parser.add_argument("--dwell-minutes", type=int, default=0)
    parser.add_argument("--apply-rollback", action="store_true")
    parser.add_argument("--require-promote", action="store_true")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--model-version", default="")
    parser.add_argument("--prompt-version", default="")
    parser.add_argument("--policy-version", default="")
    parser.add_argument("--triage-out", default="var/chat_graph/triage/chat_launch_failure_cases.jsonl")
    parser.add_argument("--triage-max-samples", type=int, default=50)
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
    parser.add_argument("--max-mismatch-ratio-increase", type=float, default=0.01)
    parser.add_argument("--max-blocker-ratio-increase", type=float, default=0.005)
    parser.add_argument("--max-reason-invalid-ratio-increase", type=float, default=0.0)
    parser.add_argument("--max-reason-unknown-ratio-increase", type=float, default=0.01)
    parser.add_argument("--max-legacy-ratio-increase", type=float, default=0.0)
    parser.add_argument("--max-insufficient-evidence-ratio-increase", type=float, default=0.05)
    parser.add_argument("--max-completion-rate-drop", type=float, default=0.03)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    release_gate_mod = _load_module("chat_release_train_gate.py")
    launch_gate_mod = _load_module("chat_production_launch_gate.py")

    launch_report_path = ""
    launch_stdout = ""
    launch_rc = 0

    if str(args.launch_gate_report).strip():
        launch_report_path = str(args.launch_gate_report)
    else:
        launch_rc, launch_stdout, launch_report_path = run_launch_gate_subprocess(
            out_dir=str(args.out),
            replay_dir=str(args.replay_dir),
            completion_source=str(args.completion_source),
            min_reason_window=int(args.min_reason_window),
            min_legacy_window=int(args.min_legacy_window),
            min_run_window=int(args.min_run_window),
            min_commerce_samples=int(args.min_commerce_samples),
            max_mismatch_ratio=float(args.max_mismatch_ratio),
            max_blocker_ratio=float(args.max_blocker_ratio),
            max_reason_invalid_ratio=float(args.max_reason_invalid_ratio),
            max_reason_unknown_ratio=float(args.max_reason_unknown_ratio),
            max_legacy_ratio=float(args.max_legacy_ratio),
            max_legacy_count=int(args.max_legacy_count),
            min_completion_rate=float(args.min_commerce_completion_rate),
            max_insufficient_ratio=float(args.max_insufficient_evidence_ratio),
            model_version=str(args.model_version),
            prompt_version=str(args.prompt_version),
            policy_version=str(args.policy_version),
            baseline_report=str(args.baseline_report),
            max_mismatch_ratio_increase=float(args.max_mismatch_ratio_increase),
            max_blocker_ratio_increase=float(args.max_blocker_ratio_increase),
            max_reason_invalid_ratio_increase=float(args.max_reason_invalid_ratio_increase),
            max_reason_unknown_ratio_increase=float(args.max_reason_unknown_ratio_increase),
            max_legacy_ratio_increase=float(args.max_legacy_ratio_increase),
            max_insufficient_ratio_increase=float(args.max_insufficient_evidence_ratio_increase),
            max_completion_rate_drop=float(args.max_completion_rate_drop),
            triage_out=str(args.triage_out),
            triage_max_samples=int(args.triage_max_samples),
        )
    if not str(launch_report_path).strip():
        raise RuntimeError("launch gate report path could not be resolved")

    launch_report = load_json(Path(launch_report_path))
    decision = release_gate_mod.decide_release_train(
        launch_report,
        current_stage=int(args.current_stage),
        dwell_minutes=max(0, int(args.dwell_minutes)),
    )

    rollback_payload = None
    if args.apply_rollback and str(decision.get("action")) == "rollback":
        derived = launch_report.get("derived") if isinstance(launch_report.get("derived"), Mapping) else {}
        canary = derived.get("canary") if isinstance(derived.get("canary"), Mapping) else {}
        _bootstrap_path = getattr(release_gate_mod, "_bootstrap_pythonpath", None)
        if callable(_bootstrap_path):
            _bootstrap_path()
        from app.core.chat_graph.canary_controller import CanaryGateDecision, apply_auto_rollback

        rollback_input = CanaryGateDecision(
            passed=False,
            gate_status=str(canary.get("gate_status") or "BLOCK"),
            reason=str(decision.get("reason") or "launch_gate_failed"),
            blocker_ratio=float(canary.get("blocker_ratio") or 0.0),
            mismatch_ratio=float(canary.get("mismatch_ratio") or 0.0),
        )
        rollback = apply_auto_rollback(
            rollback_input,
            trace_id=f"liveops_trace_{int(datetime.now(timezone.utc).timestamp())}",
            request_id=f"liveops_req_{int(datetime.now(timezone.utc).timestamp())}",
            source="chat_liveops_cycle",
        )
        rollback_payload = {
            "applied": rollback.applied,
            "mode": rollback.mode,
            "reason": rollback.reason,
            "cooldown_until": rollback.cooldown_until,
        }

    failures: list[str] = []
    gate = launch_report.get("gate") if isinstance(launch_report.get("gate"), Mapping) else {}
    if not bool(gate.get("pass")):
        failures.extend([str(item) for item in gate.get("failures") or [] if isinstance(item, str)])
        failures.extend([str(item) for item in gate.get("baseline_failures") or [] if isinstance(item, str)])
    if launch_rc not in {0, 2}:
        failures.append(f"launch gate execution error: rc={launch_rc}")

    action = str(decision.get("action") or "")
    if args.require_promote and action != "promote":
        failures.append(f"require_promote enabled but action={action}")

    cycle_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_profile": launch_report.get("release_profile"),
        "launch_gate_report_path": str(launch_report_path),
        "launch_gate": {
            "generated_at": str(launch_report.get("generated_at") or ""),
            "pass": bool(gate.get("pass")),
            "failures": list(gate.get("failures") or []),
            "baseline_failures": list(gate.get("baseline_failures") or []),
            "stdout": launch_stdout if launch_stdout else None,
            "rc": int(launch_rc),
        },
        "release_train": {
            "stage": int(args.current_stage),
            "dwell_minutes": max(0, int(args.dwell_minutes)),
            "decision": decision,
            "rollback": rollback_payload,
        },
        "failures": failures,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{args.prefix}_{stamp}.json"
    md_path = out_dir / f"{args.prefix}_{stamp}.md"
    json_path.write_text(json.dumps(cycle_report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(cycle_report), encoding="utf-8")

    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    print(f"release_action={action}")
    print(f"cycle_pass={str(len(failures) == 0).lower()}")

    if failures:
        for item in failures:
            print(f"[cycle-failure] {item}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
