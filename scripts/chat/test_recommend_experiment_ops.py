import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "recommend_experiment_ops.py"
    spec = importlib.util.spec_from_file_location("recommend_experiment_ops", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_snapshot_uses_get_with_admin_header(monkeypatch):
    module = _load_module()
    captured = {}

    def fake_http(method, url, headers, payload, *, timeout_sec=10.0):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        captured["timeout_sec"] = timeout_sec
        return 200, {"status": "ok"}

    monkeypatch.setattr(module, "_http_request_json", fake_http)
    monkeypatch.setattr(
        "sys.argv",
        [
            "recommend_experiment_ops.py",
            "--base-url",
            "http://localhost:8088/",
            "--admin-id",
            "7",
            "snapshot",
        ],
    )

    assert module.main() == 0
    assert captured["method"] == "GET"
    assert captured["url"] == "http://localhost:8088/chat/recommend/experiment"
    assert captured["headers"]["x-admin-id"] == "7"
    assert captured["payload"] == {}


def test_config_supports_payload_json_and_output_file(tmp_path, monkeypatch):
    module = _load_module()
    output_path = tmp_path / "config_response.json"
    captured = {}

    def fake_http(method, url, headers, payload, *, timeout_sec=10.0):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return 200, {"status": "ok", "experiment": {"diversity_percent": 70}}

    monkeypatch.setattr(module, "_http_request_json", fake_http)
    monkeypatch.setattr(
        "sys.argv",
        [
            "recommend_experiment_ops.py",
            "--base-url",
            "http://localhost:8088",
            "--payload-json",
            '{"overrides":{"diversity_percent":70}}',
            "--output",
            str(output_path),
            "config",
        ],
    )

    assert module.main() == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8088/chat/recommend/experiment/config"
    assert captured["payload"]["overrides"]["diversity_percent"] == 70
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["status"] == "ok"


def test_config_without_payload_fails():
    module = _load_module()
    import sys

    argv_backup = sys.argv
    try:
        sys.argv = ["recommend_experiment_ops.py", "config"]
        assert module.main() == 2
    finally:
        sys.argv = argv_backup
