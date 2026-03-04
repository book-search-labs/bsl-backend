import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_replay_sandbox_runtime.py"
    spec = importlib.util.spec_from_file_location("chat_replay_sandbox_runtime", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_sandbox_runtime_tracks_parity_and_determinism():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-03T00:00:00Z",
            "scenario_id": "s1",
            "mode": "MOCK",
            "result": "PASS",
            "seed": "seed-1",
            "response_hash": "h1",
        },
        {
            "timestamp": "2026-03-03T00:01:00Z",
            "scenario_id": "s1",
            "mode": "REAL",
            "result": "PASS",
            "seed": "seed-1",
            "response_hash": "h2",
        },
        {
            "timestamp": "2026-03-03T00:02:00Z",
            "scenario_id": "s2",
            "mode": "MOCK",
            "result": "PASS",
            "seed": "seed-2",
            "response_hash": "h3",
        },
        {
            "timestamp": "2026-03-03T00:03:00Z",
            "scenario_id": "s2",
            "mode": "MOCK",
            "result": "PASS",
            "seed": "seed-2",
            "response_hash": "h4",
        },
        {
            "timestamp": "2026-03-03T00:04:00Z",
            "scenario_id": "s2",
            "mode": "REAL",
            "result": "UNKNOWN_RESULT",
            "seed": "",
            "response_hash": "",
        },
    ]
    summary = module.summarize_sandbox_runtime(
        rows,
        now=datetime(2026, 3, 3, 0, 5, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 5
    assert summary["mock_total"] == 3
    assert summary["real_total"] == 2
    assert summary["missing_mode_total"] == 0
    assert summary["invalid_result_total"] == 1
    assert summary["missing_seed_total"] == 1
    assert summary["missing_response_hash_total"] == 1
    assert summary["parity_pair_total"] == 1
    assert summary["parity_mismatch_total"] == 1
    assert summary["non_deterministic_total"] == 1
    assert summary["stale_minutes"] == 1.0


def test_evaluate_gate_detects_sandbox_runtime_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "mock_total": 1,
            "real_total": 1,
            "parity_mismatch_total": 2,
            "non_deterministic_total": 1,
            "missing_mode_total": 1,
            "invalid_result_total": 1,
            "missing_seed_total": 1,
            "missing_response_hash_total": 1,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_mock_total=2,
        min_real_total=2,
        max_parity_mismatch_total=0,
        max_non_deterministic_total=0,
        max_missing_mode_total=0,
        max_invalid_result_total=0,
        max_missing_seed_total=0,
        max_missing_response_hash_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_min_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "mock_total": 0,
            "real_total": 0,
            "parity_mismatch_total": 0,
            "non_deterministic_total": 0,
            "missing_mode_total": 0,
            "invalid_result_total": 0,
            "missing_seed_total": 0,
            "missing_response_hash_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_mock_total=0,
        min_real_total=0,
        max_parity_mismatch_total=1000000,
        max_non_deterministic_total=1000000,
        max_missing_mode_total=1000000,
        max_invalid_result_total=1000000,
        max_missing_seed_total=1000000,
        max_missing_response_hash_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []


def test_compare_with_baseline_detects_sandbox_runtime_regressions():
    module = _load_module()
    baseline = {
        "summary": {
            "mock_total": 20,
            "real_total": 20,
            "parity_mismatch_total": 0,
            "non_deterministic_total": 0,
            "missing_mode_total": 0,
            "invalid_result_total": 0,
            "missing_seed_total": 0,
            "missing_response_hash_total": 0,
            "parity_match_ratio": 1.0,
            "stale_minutes": 10.0,
        }
    }
    failures = module.compare_with_baseline(
        baseline,
        {
            "mock_total": 1,
            "real_total": 1,
            "parity_mismatch_total": 2,
            "non_deterministic_total": 1,
            "missing_mode_total": 1,
            "invalid_result_total": 1,
            "missing_seed_total": 1,
            "missing_response_hash_total": 1,
            "parity_match_ratio": 0.2,
            "stale_minutes": 80.0,
        },
        max_mock_total_drop=1,
        max_real_total_drop=1,
        max_parity_mismatch_total_increase=0,
        max_non_deterministic_total_increase=0,
        max_missing_mode_total_increase=0,
        max_invalid_result_total_increase=0,
        max_missing_seed_total_increase=0,
        max_missing_response_hash_total_increase=0,
        max_parity_match_ratio_drop=0.05,
        max_stale_minutes_increase=30.0,
    )
    assert any("mock_total regression" in item for item in failures)
    assert any("real_total regression" in item for item in failures)
    assert any("parity_mismatch_total regression" in item for item in failures)
    assert any("non_deterministic_total regression" in item for item in failures)
    assert any("missing_mode_total regression" in item for item in failures)
    assert any("invalid_result_total regression" in item for item in failures)
    assert any("missing_seed_total regression" in item for item in failures)
    assert any("missing_response_hash_total regression" in item for item in failures)
    assert any("parity_match_ratio regression" in item for item in failures)
    assert any("stale minutes regression" in item for item in failures)
