import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_legacy_decommission_check.py"
    spec = importlib.util.spec_from_file_location("chat_legacy_decommission_check", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_evaluate_gate_passes_when_legacy_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 25,
            "legacy_count": 0,
            "legacy_ratio": 0.0,
            "legacy_reason_counts": {},
        },
        min_window=20,
        max_legacy_count=0,
        max_legacy_ratio=0.0,
        allow_legacy_reasons=set(),
    )
    assert failures == []


def test_evaluate_gate_fails_when_disallowed_legacy_reason_exists():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 30,
            "legacy_count": 1,
            "legacy_ratio": 0.03,
            "legacy_reason_counts": {"force_legacy": 1},
        },
        min_window=20,
        max_legacy_count=2,
        max_legacy_ratio=0.1,
        allow_legacy_reasons={"legacy_emergency_recovery"},
    )
    assert len(failures) == 1
    assert "disallowed legacy reasons detected" in failures[0]


def test_evaluate_gate_detects_count_ratio_and_window_violation():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "legacy_count": 2,
            "legacy_ratio": 0.4,
            "legacy_reason_counts": {"force_legacy": 2},
        },
        min_window=20,
        max_legacy_count=0,
        max_legacy_ratio=0.0,
        allow_legacy_reasons=set(),
    )
    assert len(failures) == 3
    assert any("insufficient routing samples" in item for item in failures)
    assert any("legacy count exceeded" in item for item in failures)
    assert any("legacy ratio exceeded" in item for item in failures)


def test_compare_with_baseline_detects_legacy_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "legacy_count": 0,
                "legacy_ratio": 0.0,
            }
        }
    }
    current = {
        "legacy_count": 2,
        "legacy_ratio": 0.02,
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_legacy_count_increase=0,
        max_legacy_ratio_increase=0.0,
    )
    assert any("legacy count regression" in item for item in failures)
    assert any("legacy ratio regression" in item for item in failures)
