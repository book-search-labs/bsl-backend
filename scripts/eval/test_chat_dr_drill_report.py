import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_dr_drill_report.py"
    spec = importlib.util.spec_from_file_location("chat_dr_drill_report", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_drill_summary_recovers_single_drill(tmp_path: Path):
    module = _load_module()
    rows = [
        {
            "generated_at": "2026-03-02T12:00:00+00:00",
            "release_train": {"decision": {"action": "rollback", "reason": "gate_failed"}},
            "failures": ["x"],
        },
        {
            "generated_at": "2026-03-02T12:10:00+00:00",
            "release_train": {"decision": {"action": "promote", "reason": "recovered"}},
            "failures": [],
        },
    ]
    paths: list[Path] = []
    for idx, row in enumerate(rows):
        path = tmp_path / f"chat_liveops_cycle_20260302_12000{idx}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        paths.append(path)

    summary = module.build_drill_summary(paths)
    assert summary["drill_total"] == 1
    assert summary["recovered_total"] == 1
    assert summary["open_drill_total"] == 0
    assert summary["recovery_ratio"] == 1.0
    assert summary["avg_mttr_sec"] > 0.0


def test_evaluate_gate_detects_missing_required_drill():
    module = _load_module()
    summary = {
        "window_size": 4,
        "drill_total": 0,
        "recovery_ratio": 1.0,
        "open_drill_total": 0,
        "avg_mttr_sec": 0.0,
    }
    failures = module.evaluate_gate(
        summary,
        min_window=3,
        require_drill=True,
        min_recovery_ratio=1.0,
        max_open_drill_total=0,
        max_avg_mttr_sec=7200.0,
    )
    assert len(failures) == 1
    assert "no rollback drill observed" in failures[0]


def test_evaluate_gate_detects_open_drill():
    module = _load_module()
    summary = {
        "window_size": 4,
        "drill_total": 2,
        "recovery_ratio": 0.5,
        "open_drill_total": 1,
        "avg_mttr_sec": 60.0,
    }
    failures = module.evaluate_gate(
        summary,
        min_window=3,
        require_drill=False,
        min_recovery_ratio=0.7,
        max_open_drill_total=0,
        max_avg_mttr_sec=7200.0,
    )
    assert len(failures) == 2
    assert any("recovery ratio below threshold" in item for item in failures)
    assert any("open drill count exceeded" in item for item in failures)


def test_compare_with_baseline_detects_recovery_open_mttr_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "recovery_ratio": 1.0,
                "open_drill_total": 0,
                "avg_mttr_sec": 60.0,
            }
        }
    }
    current = {
        "recovery_ratio": 0.5,
        "open_drill_total": 2,
        "avg_mttr_sec": 600.0,
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_recovery_ratio_drop=0.1,
        max_open_drill_increase=0,
        max_avg_mttr_sec_increase=30.0,
    )
    assert any("recovery ratio regression" in item for item in failures)
    assert any("open drill regression" in item for item in failures)
    assert any("avg MTTR regression" in item for item in failures)
