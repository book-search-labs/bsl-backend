import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_agent_eval_summary.py"
    spec = importlib.util.spec_from_file_location("chat_agent_eval_summary", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def _write_report(path: Path, *, gate_pass: bool, generated_at: str) -> None:
    payload = {
        "generated_at": generated_at,
        "gate": {
            "pass": gate_pass,
            "failures": [] if gate_pass else ["failed gate"],
            "baseline_failures": [],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_summarize_components_reads_latest_files(tmp_path):
    module = _load_module()
    _write_report(tmp_path / "chat_recommend_eval_20260301_000001.json", gate_pass=True, generated_at="2026-03-01T00:00:01+00:00")
    _write_report(tmp_path / "chat_recommend_eval_20260301_000002.json", gate_pass=False, generated_at="2026-03-01T00:00:02+00:00")
    summary = module.summarize_components(tmp_path)
    recommend = summary["recommend"]
    assert recommend["present"] is True
    assert recommend["gate_pass"] is False
    assert recommend["generated_at"] == "2026-03-01T00:00:02+00:00"


def test_evaluate_overall_with_require_all_flags_missing():
    module = _load_module()
    summary = {
        "recommend": {"present": True, "gate_pass": True, "failures": []},
        "rollout": {"present": False, "gate_pass": None, "failures": []},
    }
    passed, failures = module.evaluate_overall(summary, require_all=True)
    assert passed is False
    assert any("missing component report: rollout" in item for item in failures)


def test_evaluate_overall_collects_component_failures():
    module = _load_module()
    summary = {
        "recommend": {"present": True, "gate_pass": True, "failures": []},
        "rollout": {"present": True, "gate_pass": False, "failures": ["failure one"]},
    }
    passed, failures = module.evaluate_overall(summary, require_all=False)
    assert passed is False
    assert failures == ["rollout: failure one"]


def test_main_writes_summary_reports(tmp_path, monkeypatch):
    module = _load_module()
    _write_report(tmp_path / "chat_recommend_eval_20260301_000001.json", gate_pass=True, generated_at="2026-03-01T00:00:01+00:00")
    _write_report(tmp_path / "chat_rollout_eval_20260301_000001.json", gate_pass=True, generated_at="2026-03-01T00:00:01+00:00")
    _write_report(tmp_path / "chat_semantic_cache_eval_20260301_000001.json", gate_pass=True, generated_at="2026-03-01T00:00:01+00:00")
    _write_report(tmp_path / "chat_regression_suite_eval_20260301_000001.json", gate_pass=True, generated_at="2026-03-01T00:00:01+00:00")
    monkeypatch.setattr(
        "sys.argv",
        [
            "chat_agent_eval_summary.py",
            "--reports-dir",
            str(tmp_path),
            "--out",
            str(tmp_path),
            "--gate",
            "--require-all",
        ],
    )
    assert module.main() == 0
    reports = sorted(tmp_path.glob("chat_agent_eval_summary_*.json"))
    assert reports
    loaded = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert loaded["gate"]["pass"] is True
