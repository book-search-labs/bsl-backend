import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_immutable_bundle_guard.py"
    spec = importlib.util.spec_from_file_location("chat_immutable_bundle_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_bundle_summary_tracks_signature_changes(tmp_path: Path):
    module = _load_module()
    rows = [
        {
            "generated_at": "2026-03-02T12:00:00+00:00",
            "release_profile": {"release_signature": "sig-a"},
            "release_train": {"decision": {"action": "promote"}},
        },
        {
            "generated_at": "2026-03-02T12:05:00+00:00",
            "release_profile": {"release_signature": "sig-b"},
            "release_train": {"decision": {"action": "rollback"}},
        },
    ]
    paths: list[Path] = []
    for idx, row in enumerate(rows):
        path = tmp_path / f"chat_liveops_cycle_20260302_12000{idx}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        paths.append(path)

    summary = module.build_bundle_summary(paths)
    assert summary["window_size"] == 2
    assert summary["signature_change_count"] == 1
    assert summary["unique_signature_count"] == 2


def test_evaluate_gate_detects_disallowed_signature_change():
    module = _load_module()
    summary = {
        "window_size": 5,
        "missing_signature_count": 0,
        "unique_signature_count": 2,
        "signature_change_count": 1,
        "signature_changes": [
            {
                "from_signature": "sig-a",
                "to_signature": "sig-b",
                "action": "hold",
            }
        ],
    }
    failures = module.evaluate_gate(
        summary,
        min_window=3,
        max_unique_signatures=2,
        max_signature_changes=2,
        allowed_change_actions={"promote", "rollback"},
        require_signature=True,
    )
    assert len(failures) == 1
    assert "disallowed action" in failures[0]


def test_evaluate_gate_detects_missing_signature():
    module = _load_module()
    summary = {
        "window_size": 4,
        "missing_signature_count": 1,
        "unique_signature_count": 1,
        "signature_change_count": 0,
        "signature_changes": [],
    }
    failures = module.evaluate_gate(
        summary,
        min_window=3,
        max_unique_signatures=2,
        max_signature_changes=2,
        allowed_change_actions={"promote", "rollback"},
        require_signature=True,
    )
    assert len(failures) == 1
    assert "missing release_signature observed" in failures[0]


def test_compare_with_baseline_detects_signature_regression():
    module = _load_module()
    baseline = {
        "derived": {
            "summary": {
                "missing_signature_count": 0,
                "unique_signature_count": 1,
                "signature_change_count": 0,
            }
        }
    }
    current = {
        "missing_signature_count": 2,
        "unique_signature_count": 3,
        "signature_change_count": 4,
    }
    failures = module.compare_with_baseline(
        baseline,
        current,
        max_missing_signature_increase=0,
        max_unique_signature_increase=0,
        max_signature_change_increase=0,
    )
    assert any("missing signature regression" in item for item in failures)
    assert any("unique signature regression" in item for item in failures)
    assert any("signature change regression" in item for item in failures)
