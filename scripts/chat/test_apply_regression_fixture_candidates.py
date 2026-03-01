import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "apply_regression_fixture_candidates.py"
    spec = importlib.util.spec_from_file_location("apply_regression_fixture_candidates", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_apply_candidates_skips_review_without_flag():
    module = _load_module()
    fixture = {"scenarios": [{"id": "S1", "turns": [{"query": "a"}]}]}
    candidates = {
        "candidates": [
            {
                "scenario_id": "F_NEW_1",
                "review_required": True,
                "scenario": {"id": "F_NEW_1", "turns": [{"query": "b"}]},
            }
        ]
    }
    updated, report = module.apply_candidates(
        fixture,
        candidates,
        selected_ids=None,
        max_add=0,
        allow_review_required=False,
    )
    assert len(updated["scenarios"]) == 1
    assert report["added_count"] == 0
    assert report["skipped_review_count"] == 1


def test_apply_candidates_selected_ids_and_allow_review():
    module = _load_module()
    fixture = {"scenarios": [{"id": "S1", "turns": [{"query": "a"}]}]}
    candidates = {
        "candidates": [
            {
                "scenario_id": "F_NEW_1",
                "review_required": True,
                "reason_code": "MISSING_INPUT",
                "count": 4,
                "source_item_id": "feedback.reason.missing_input",
                "scenario": {"id": "F_NEW_1", "turns": [{"query": "b"}]},
            },
            {
                "scenario_id": "F_NEW_2",
                "review_required": False,
                "scenario": {"id": "F_NEW_2", "turns": [{"query": "c"}]},
            },
        ]
    }
    updated, report = module.apply_candidates(
        fixture,
        candidates,
        selected_ids={"F_NEW_1"},
        max_add=0,
        allow_review_required=True,
    )
    ids = [s["id"] for s in updated["scenarios"]]
    assert ids == ["S1", "F_NEW_1"]
    assert report["added_count"] == 1
    assert report["added_items"][0]["scenario_id"] == "F_NEW_1"
    assert report["skipped_not_selected_count"] == 1


def test_main_dry_run_writes_reports_only(tmp_path, monkeypatch):
    module = _load_module()
    fixture_path = tmp_path / "fixture.json"
    candidates_path = tmp_path / "candidates.json"
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"
    fixture_path.write_text(json.dumps({"suite": "v1", "scenarios": [{"id": "S1", "turns": [{"query": "a"}]}]}), encoding="utf-8")
    candidates_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "scenario_id": "F_NEW_1",
                        "review_required": False,
                        "scenario": {"id": "F_NEW_1", "turns": [{"query": "b"}]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    before = fixture_path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "apply_regression_fixture_candidates.py",
            "--fixture",
            str(fixture_path),
            "--candidates-json",
            str(candidates_path),
            "--report-json",
            str(report_json),
            "--report-md",
            str(report_md),
            "--dry-run",
        ],
    )
    assert module.main() == 0
    assert fixture_path.read_text(encoding="utf-8") == before
    assert report_json.exists()
    assert report_md.exists()


def test_main_without_allow_empty_fails_on_empty_candidates(tmp_path, monkeypatch):
    module = _load_module()
    fixture_path = tmp_path / "fixture.json"
    candidates_path = tmp_path / "candidates.json"
    fixture_path.write_text(json.dumps({"suite": "v1", "scenarios": []}), encoding="utf-8")
    candidates_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "apply_regression_fixture_candidates.py",
            "--fixture",
            str(fixture_path),
            "--candidates-json",
            str(candidates_path),
        ],
    )
    assert module.main() == 1
