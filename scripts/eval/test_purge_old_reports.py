import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "purge_old_reports.py"
    spec = importlib.util.spec_from_file_location("purge_old_reports", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_collect_entries_groups_json_and_markdown(tmp_path):
    module = _load_module()
    _touch(tmp_path / "chat_recommend_eval_20260301_010101.json")
    _touch(tmp_path / "chat_recommend_eval_20260301_010101.md")
    _touch(tmp_path / "chat_recommend_eval_baseline.json")

    entries = module.collect_entries(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.prefix == "chat_recommend_eval"
    assert entry.stamp == "20260301_010101"
    assert len(entry.files) == 2


def test_plan_purge_keeps_latest_then_deletes_old_by_cutoff(tmp_path):
    module = _load_module()
    _touch(tmp_path / "chat_recommend_eval_20260101_000000.json")
    _touch(tmp_path / "chat_recommend_eval_20260220_000000.json")
    _touch(tmp_path / "chat_recommend_eval_20260225_000000.json")

    entries = module.collect_entries(tmp_path)
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    plan = module.plan_purge(entries, now=now, retention_days=10, keep_latest_per_prefix=1)

    delete_entries = plan["delete_entries"]
    delete_stamps = sorted(item.stamp for item in delete_entries)
    assert delete_stamps == ["20260101_000000"]


def test_main_dry_run_reports_deletions_without_removing_files(tmp_path, monkeypatch):
    module = _load_module()
    old_json = tmp_path / "chat_rollout_eval_20200101_000000.json"
    old_md = tmp_path / "chat_rollout_eval_20200101_000000.md"
    _touch(old_json)
    _touch(old_md)

    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "purge_old_reports.py",
            "--reports-dir",
            str(tmp_path),
            "--retention-days",
            "30",
            "--keep-latest-per-prefix",
            "0",
            "--dry-run",
            "--summary-json",
            str(summary_path),
        ],
    )
    assert module.main() == 0

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["totals"]["delete_entries"] == 1
    assert payload["totals"]["delete_files"] == 2
    assert old_json.exists()
    assert old_md.exists()


def test_main_apply_deletes_old_timestamped_files_only(tmp_path, monkeypatch):
    module = _load_module()
    old_json = tmp_path / "chat_semantic_cache_eval_20200101_000000.json"
    old_md = tmp_path / "chat_semantic_cache_eval_20200101_000000.md"
    recent_json = tmp_path / "chat_semantic_cache_eval_20990101_000000.json"
    baseline = tmp_path / "chat_semantic_cache_eval_baseline.json"
    _touch(old_json)
    _touch(old_md)
    _touch(recent_json)
    _touch(baseline)

    monkeypatch.setattr(
        "sys.argv",
        [
            "purge_old_reports.py",
            "--reports-dir",
            str(tmp_path),
            "--retention-days",
            "30",
            "--keep-latest-per-prefix",
            "1",
        ],
    )
    assert module.main() == 0

    assert old_json.exists() is False
    assert old_md.exists() is False
    assert recent_json.exists() is True
    assert baseline.exists() is True
