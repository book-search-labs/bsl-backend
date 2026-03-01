import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "build_regression_seed_fixture.py"
    spec = importlib.util.spec_from_file_location("build_regression_seed_fixture", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_build_candidate_payload_skips_existing_and_accepts_new():
    module = _load_module()
    seeds_payload = {
        "items": [
            {
                "id": "feedback.reason.auth_required",
                "reason_code": "AUTH_REQUIRED",
                "count": 4,
                "title": "auth required spike",
                "scenario_stub": {
                    "id": "S01_order_lookup_requires_auth",
                    "turns": [{"query": "주문 조회", "expected": {"reason_code": "AUTH_REQUIRED"}}],
                },
            },
            {
                "id": "feedback.reason.missing_input",
                "reason_code": "MISSING_INPUT",
                "count": 3,
                "title": "missing input spike",
                "scenario_stub": {
                    "id": "F_missing_input",
                    "turns": [{"query": "그거 해줘", "expected": {"reason_code": "MISSING_INPUT"}}],
                },
            },
        ]
    }
    base_fixture = {
        "scenarios": [
            {"id": "S01_order_lookup_requires_auth", "turns": [{"query": "x"}]},
        ]
    }
    payload = module.build_candidate_payload(seeds_payload, base_fixture=base_fixture)
    summary = payload["summary"]
    assert summary["base_scenario_count"] == 1
    assert summary["accepted_count"] == 1
    assert summary["skipped_existing_count"] == 1
    candidates = payload["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["scenario_id"] == "F_missing_input"
    assert candidates[0]["review_required"] is True


def test_main_allow_empty_writes_outputs(tmp_path, monkeypatch):
    module = _load_module()
    seeds_path = tmp_path / "seeds.json"
    base_fixture_path = tmp_path / "fixture.json"
    output_json = tmp_path / "candidates.json"
    output_md = tmp_path / "candidates.md"
    seeds_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    base_fixture_path.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_regression_seed_fixture.py",
            "--seeds-json",
            str(seeds_path),
            "--base-fixture",
            str(base_fixture_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--allow-empty",
        ],
    )
    assert module.main() == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["summary"]["accepted_count"] == 0
    assert "no fixture candidates" in output_md.read_text(encoding="utf-8")


def test_main_without_allow_empty_fails(tmp_path, monkeypatch):
    module = _load_module()
    seeds_path = tmp_path / "seeds.json"
    base_fixture_path = tmp_path / "fixture.json"
    output_json = tmp_path / "candidates.json"
    output_md = tmp_path / "candidates.md"
    seeds_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    base_fixture_path.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_regression_seed_fixture.py",
            "--seeds-json",
            str(seeds_path),
            "--base-fixture",
            str(base_fixture_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
    )
    assert module.main() == 1
    assert not output_json.exists()
