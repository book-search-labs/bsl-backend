import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parent / "chat_prompt_signature_verification_guard.py"
    spec = importlib.util.spec_from_file_location("chat_prompt_signature_verification_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_summarize_prompt_signature_verification_guard_tracks_tamper_blocking():
    module = _load_module()
    rows = [
        {
            "timestamp": "2026-03-04T00:00:00Z",
            "artifact_id": "a1",
            "signature_present": True,
            "signer_trusted": True,
            "checksum_match": True,
            "verify_result": "success",
            "deploy_allowed": True,
        },
        {
            "timestamp": "2026-03-04T00:00:20Z",
            "artifact_id": "a2",
            "signature_present": False,
            "verify_result": "missing_signature",
            "deploy_allowed": False,
            "reason_code": "PROMPT_SIGNATURE_MISSING",
        },
        {
            "timestamp": "2026-03-04T00:00:30Z",
            "artifact_id": "a3",
            "signature_present": True,
            "signer_trusted": False,
            "checksum_match": False,
            "verify_result": "untrusted_signer",
            "deploy_allowed": True,
            "reason_code": "",
        },
    ]

    summary = module.summarize_prompt_signature_verification_guard(
        rows,
        now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert summary["window_size"] == 3
    assert summary["artifact_total"] == 3
    assert summary["signature_verified_total"] == 1
    assert abs(summary["signature_verified_ratio"] - (1.0 / 3.0)) < 1e-9
    assert summary["signature_verify_fail_total"] == 2
    assert summary["unsigned_artifact_total"] == 1
    assert summary["untrusted_signer_total"] == 1
    assert summary["checksum_mismatch_total"] == 1
    assert summary["deploy_block_total"] == 1
    assert summary["unblocked_tampered_total"] == 1
    assert summary["reason_code_missing_total"] == 1
    assert summary["stale_minutes"] == 0.5


def test_evaluate_gate_detects_prompt_signature_verification_failures():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 5,
            "artifact_total": 1,
            "signature_verified_ratio": 0.1,
            "signature_verify_fail_total": 3,
            "unsigned_artifact_total": 2,
            "untrusted_signer_total": 1,
            "checksum_mismatch_total": 1,
            "unblocked_tampered_total": 1,
            "reason_code_missing_total": 2,
            "stale_minutes": 120.0,
        },
        min_window=10,
        min_artifact_total=2,
        min_signature_verified_ratio=0.95,
        max_signature_verify_fail_total=0,
        max_unsigned_artifact_total=0,
        max_untrusted_signer_total=0,
        max_checksum_mismatch_total=0,
        max_unblocked_tampered_total=0,
        max_reason_code_missing_total=0,
        max_stale_minutes=60.0,
    )
    assert len(failures) == 10


def test_evaluate_gate_allows_empty_when_minimums_are_zero():
    module = _load_module()
    failures = module.evaluate_gate(
        {
            "window_size": 0,
            "artifact_total": 0,
            "signature_verified_ratio": 1.0,
            "signature_verify_fail_total": 0,
            "unsigned_artifact_total": 0,
            "untrusted_signer_total": 0,
            "checksum_mismatch_total": 0,
            "unblocked_tampered_total": 0,
            "reason_code_missing_total": 0,
            "stale_minutes": 0.0,
        },
        min_window=0,
        min_artifact_total=0,
        min_signature_verified_ratio=0.0,
        max_signature_verify_fail_total=1000000,
        max_unsigned_artifact_total=1000000,
        max_untrusted_signer_total=1000000,
        max_checksum_mismatch_total=1000000,
        max_unblocked_tampered_total=1000000,
        max_reason_code_missing_total=1000000,
        max_stale_minutes=1000000.0,
    )
    assert failures == []
