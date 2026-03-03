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
