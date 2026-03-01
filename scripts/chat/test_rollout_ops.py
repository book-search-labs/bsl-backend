import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "rollout_ops.py"
    spec = importlib.util.spec_from_file_location("rollout_ops", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_rollout_snapshot_uses_get_with_admin_header(monkeypatch):
    module = _load_module()
    captured = {}

    def fake_http(method, url, headers, payload, *, timeout_sec):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return 200, {"status": "ok"}

    monkeypatch.setattr(module, "_http_request_json", fake_http)
    monkeypatch.setattr(
        "sys.argv",
        [
            "rollout_ops.py",
            "--base-url",
            "http://localhost:8088/",
            "--admin-id",
            "7",
            "snapshot",
        ],
    )

    assert module.main() == 0
    assert captured["method"] == "GET"
    assert captured["url"] == "http://localhost:8088/chat/rollout"
    assert captured["headers"]["x-admin-id"] == "7"
    assert captured["payload"] == {}


def test_rollout_reset_writes_output_file(tmp_path, monkeypatch):
    module = _load_module()
    output_path = tmp_path / "rollout_reset.json"
    captured = {}

    def fake_http(method, url, headers, payload, *, timeout_sec):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return 200, {"status": "ok", "reset": {"reset_applied": True}}

    monkeypatch.setattr(module, "_http_request_json", fake_http)
    monkeypatch.setattr(
        "sys.argv",
        [
            "rollout_ops.py",
            "--payload-json",
            '{"engine":"agent","clear_gate":true}',
            "--output",
            str(output_path),
            "reset",
        ],
    )

    assert module.main() == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/chat/rollout/reset")
    assert captured["payload"]["engine"] == "agent"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["status"] == "ok"


def test_rollout_ops_rejects_non_object_payload():
    module = _load_module()
    import sys

    argv_backup = sys.argv
    try:
        sys.argv = ["rollout_ops.py", "--payload-json", "[]", "reset"]
        assert module.main() == 2
    finally:
        sys.argv = argv_backup
