from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


def _base_dir() -> Path:
    raw = os.getenv("QS_CHAT_GRAPH_REPLAY_DIR", "var/chat_graph/replay").strip() or "var/chat_graph/replay"
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _runs_dir() -> Path:
    path = _base_dir() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _replays_dir() -> Path:
    path = _base_dir() / "replays"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _request_index_path() -> Path:
    return _base_dir() / "request_index.json"


def _run_path(run_id: str) -> Path:
    safe = _safe_id(run_id)
    return _runs_dir() / f"{safe}.json"


def _replay_path(replay_id: str) -> Path:
    safe = _safe_id(replay_id)
    return _replays_dir() / f"{safe}.json"


def _safe_id(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "unknown"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", ":"} else "_" for ch in text)
    return safe[:128]


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _state_minimal(state: dict[str, Any]) -> dict[str, Any]:
    pending = state.get("pending_action") if isinstance(state.get("pending_action"), dict) else None
    response = state.get("response") if isinstance(state.get("response"), dict) else None
    return {
        "schema_version": state.get("schema_version"),
        "state_version": state.get("state_version"),
        "trace_id": state.get("trace_id"),
        "request_id": state.get("request_id"),
        "session_id": state.get("session_id"),
        "intent": state.get("intent"),
        "route": state.get("route"),
        "reason_code": state.get("reason_code"),
        "pending_action": pending,
        "response": {
            "status": response.get("status"),
            "reason_code": response.get("reason_code"),
            "next_action": response.get("next_action"),
        }
        if response
        else None,
    }


def _state_hash(minimal_state: dict[str, Any]) -> str:
    encoded = json.dumps(minimal_state, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _update_request_index(request_id: str, run_id: str) -> None:
    if not request_id:
        return
    path = _request_index_path()
    payload = _load_json(path) or {}
    entries = payload.get("entries") if isinstance(payload.get("entries"), dict) else {}
    entries[str(request_id)] = {
        "run_id": run_id,
        "updated_at": int(time.time()),
    }
    payload["entries"] = entries
    _write_json(path, payload)


def resolve_run_id(request_id: str) -> str | None:
    path = _request_index_path()
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return None
    entries = payload.get("entries") if isinstance(payload.get("entries"), dict) else {}
    item = entries.get(request_id)
    if isinstance(item, dict):
        run_id = item.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            return run_id
    return None


def start_run_record(
    *,
    run_id: str,
    trace_id: str,
    request_id: str,
    session_id: str,
    request_payload: dict[str, Any],
    replay_payload: dict[str, Any],
) -> None:
    record = {
        "run_id": run_id,
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "status": "running",
        "started_at": int(time.time()),
        "updated_at": int(time.time()),
        "request_payload": request_payload,
        "replay_payload": replay_payload,
        "checkpoints": [],
        "response": None,
        "stage": None,
        "stub_response": None,
    }
    _write_json(_run_path(run_id), record)
    _update_request_index(request_id, run_id)


def append_checkpoint(run_id: str, node: str, state: dict[str, Any]) -> None:
    path = _run_path(run_id)
    record = _load_json(path)
    if not isinstance(record, dict):
        return

    checkpoints = record.get("checkpoints") if isinstance(record.get("checkpoints"), list) else []
    minimal_state = _state_minimal(state)
    checkpoints.append(
        {
            "node": node,
            "updated_at": int(time.time()),
            "state_hash": _state_hash(minimal_state),
            "state": minimal_state,
        }
    )
    record["checkpoints"] = checkpoints
    record["updated_at"] = int(time.time())
    _write_json(path, record)


def finish_run(
    run_id: str,
    *,
    stage: str,
    response: dict[str, Any],
    stub_response: dict[str, Any] | None,
) -> None:
    path = _run_path(run_id)
    record = _load_json(path)
    if not isinstance(record, dict):
        return
    record["status"] = "done"
    record["stage"] = stage
    record["response"] = response
    record["stub_response"] = stub_response
    record["updated_at"] = int(time.time())
    _write_json(path, record)


def load_run(run_id: str) -> dict[str, Any] | None:
    return _load_json(_run_path(run_id))


def save_replay(
    replay_id: str,
    *,
    run_id: str,
    request_payload: dict[str, Any],
    replay_response: dict[str, Any],
    original_response: dict[str, Any],
    diff: dict[str, Any],
    success: bool,
) -> None:
    payload = {
        "replay_id": replay_id,
        "run_id": run_id,
        "created_at": int(time.time()),
        "status": "ok" if success else "mismatch",
        "request_payload": request_payload,
        "replay_response": replay_response,
        "original_response": original_response,
        "diff": diff,
    }
    _write_json(_replay_path(replay_id), payload)


def load_replay(replay_id: str) -> dict[str, Any] | None:
    return _load_json(_replay_path(replay_id))


def response_diff(original: dict[str, Any], replayed: dict[str, Any]) -> dict[str, Any]:
    checks = [
        "status",
        "reason_code",
        "recoverable",
        "next_action",
        "retry_after_ms",
    ]
    mismatch: dict[str, dict[str, Any]] = {}
    for key in checks:
        if original.get(key) != replayed.get(key):
            mismatch[key] = {"original": original.get(key), "replayed": replayed.get(key)}

    original_answer = original.get("answer") if isinstance(original.get("answer"), dict) else {}
    replayed_answer = replayed.get("answer") if isinstance(replayed.get("answer"), dict) else {}
    if original_answer.get("content") != replayed_answer.get("content"):
        mismatch["answer.content"] = {
            "original": original_answer.get("content"),
            "replayed": replayed_answer.get("content"),
        }

    if list(original.get("citations") or []) != list(replayed.get("citations") or []):
        mismatch["citations"] = {
            "original": list(original.get("citations") or []),
            "replayed": list(replayed.get("citations") or []),
        }

    return {
        "matched": len(mismatch) == 0,
        "mismatch": mismatch,
    }
