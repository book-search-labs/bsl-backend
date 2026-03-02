import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_readiness_trend.py"
    spec = importlib.util.spec_from_file_location("chat_readiness_trend", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_trend_summary_computes_week_and_month_delta(tmp_path: Path):
    module = _load_module()
    rows = [
        {"generated_at": "2026-02-24T10:00:00+00:00", "readiness": {"total_score": 80.0, "tier": "WATCH", "recommended_action": "hold"}},
        {"generated_at": "2026-03-02T10:00:00+00:00", "readiness": {"total_score": 90.0, "tier": "READY", "recommended_action": "promote"}},
    ]
    paths: list[Path] = []
    for idx, row in enumerate(rows):
        path = tmp_path / f"chat_readiness_score_2026030{idx}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        paths.append(path)

    summary = module.build_trend_summary(paths)
    assert summary["report_total"] == 2
    assert summary["current_week_avg"] > 0.0
    assert summary["current_month_avg"] > 0.0


def test_evaluate_gate_detects_low_week_and_month():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "report_total": 3,
            "current_week_avg": 70.0,
            "current_month_avg": 75.0,
        },
        min_reports=1,
        min_week_avg=80.0,
        min_month_avg=80.0,
    )
    assert len(failures) == 2
    assert "current week average below threshold" in failures[0]


def test_evaluate_gate_detects_insufficient_reports():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "report_total": 0,
            "current_week_avg": 0.0,
            "current_month_avg": 0.0,
        },
        min_reports=1,
        min_week_avg=0.0,
        min_month_avg=0.0,
    )
    assert len(failures) == 1
    assert "insufficient readiness reports" in failures[0]
