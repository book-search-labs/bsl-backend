import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.core import chat_tools
from app.core.cache import CacheClient

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "chat_state_regression_v1.json"


def _load_suite() -> dict[str, Any]:
    with _FIXTURE_PATH.open("r", encoding="utf-8") as fp:
        loaded = json.load(fp)
    assert isinstance(loaded, dict)
    assert isinstance(loaded.get("scenarios"), list)
    return loaded


def _mock_commerce_factory(sequence_map: dict[str, list[dict[str, Any]]]):
    call_index: dict[str, int] = {}

    async def _fake_call_commerce(method: str, path: str, **kwargs):
        key = f"{str(method).upper()} {path}"
        sequence = sequence_map.get(key, [])
        index = call_index.get(key, 0)
        if index >= len(sequence):
            raise AssertionError(f"unexpected commerce call: {key}")
        call_index[key] = index + 1
        item = sequence[index]
        if isinstance(item, dict) and isinstance(item.get("error"), dict):
            error = item["error"]
            raise chat_tools.ToolCallError(
                str(error.get("code") or "tool_error"),
                str(error.get("message") or "tool_error"),
                status_code=int(error.get("status_code") or 500),
            )
        if isinstance(item, dict) and isinstance(item.get("response"), dict):
            return item["response"]
        return {}

    return _fake_call_commerce


def _mock_candidates_factory(candidate_map: dict[str, list[dict[str, Any]]]):
    async def _fake_retrieve_candidates(query: str, trace_id: str, request_id: str, top_k: int | None = None):
        return [dict(item) for item in candidate_map.get(query, [])]

    return _fake_retrieve_candidates


def _extract_confirmation_token(content: str) -> str | None:
    matched = re.search(r"\[([A-F0-9]{6})\]", str(content or ""))
    if matched:
        return matched.group(1)
    return None


def test_chat_regression_fixture_shape():
    suite = _load_suite()
    scenarios = suite.get("scenarios")
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 30
    for scenario in scenarios:
        assert isinstance(scenario, dict)
        assert isinstance(scenario.get("id"), str)
        turns = scenario.get("turns")
        assert isinstance(turns, list) and turns


def test_chat_regression_fixture_quality_guards():
    suite = _load_suite()
    scenarios = suite.get("scenarios")
    assert isinstance(scenarios, list)

    ids = [str(item.get("id") or "") for item in scenarios if isinstance(item, dict)]
    assert all(ids), "scenario id must be non-empty"
    assert len(ids) == len(set(ids)), "duplicate scenario id detected"

    multi_turn_count = 0
    for scenario in scenarios:
        assert isinstance(scenario, dict)
        turns = scenario.get("turns")
        assert isinstance(turns, list) and turns
        if len(turns) >= 2:
            multi_turn_count += 1
        for turn in turns:
            assert isinstance(turn, dict)
            query = str(turn.get("query") or "").strip()
            assert query, "turn query must be non-empty"
            expected = turn.get("expected")
            if expected is None:
                continue
            assert isinstance(expected, dict)
            has_status = isinstance(expected.get("status"), str) and bool(str(expected.get("status")).strip())
            has_reason = isinstance(expected.get("reason_code"), str) and bool(str(expected.get("reason_code")).strip())
            assert has_status or has_reason, "expected must include status or reason_code"

    # Guardrail: maintain enough multi-turn flows for transition coverage.
    assert multi_turn_count >= 12


@pytest.mark.parametrize("scenario", _load_suite()["scenarios"], ids=[s["id"] for s in _load_suite()["scenarios"]])
def test_chat_state_regression_suite(monkeypatch, scenario: dict[str, Any]):
    chat_tools._CACHE = CacheClient(None)
    session_id = str(scenario.get("session_id") or f"sess:{scenario['id']}")
    state_rows: dict[str, dict[str, Any]] = {}

    def _fake_upsert_session_state(conversation_id: str, **kwargs):
        row = dict(state_rows.get(conversation_id) or {})
        if "selection" in kwargs:
            row["selection"] = kwargs.get("selection")
        if "pending_action" in kwargs:
            row["pending_action"] = kwargs.get("pending_action")
        state_rows[conversation_id] = row
        return row

    def _fake_get_session_state(conversation_id: str):
        existing = state_rows.get(conversation_id)
        return dict(existing) if isinstance(existing, dict) else None

    monkeypatch.setattr(chat_tools, "upsert_session_state", _fake_upsert_session_state)
    monkeypatch.setattr(chat_tools, "get_durable_chat_session_state", _fake_get_session_state)
    time_state = {"now": int(scenario.get("start_time") or 1_700_000_000)}
    monkeypatch.setattr(chat_tools.time, "time", lambda: time_state["now"])
    monkeypatch.setattr(chat_tools.time, "time_ns", lambda: int(time_state["now"]) * 1_000_000_000)

    commerce_sequences = scenario.get("commerce_sequences")
    if isinstance(commerce_sequences, dict):
        normalized: dict[str, list[dict[str, Any]]] = {}
        for key, value in commerce_sequences.items():
            if isinstance(value, list):
                normalized[str(key)] = [item for item in value if isinstance(item, dict)]
        monkeypatch.setattr(chat_tools, "_call_commerce", _mock_commerce_factory(normalized))

    candidate_sequences = scenario.get("candidate_sequences")
    if isinstance(candidate_sequences, dict):
        normalized_candidates: dict[str, list[dict[str, Any]]] = {}
        for key, value in candidate_sequences.items():
            if isinstance(value, list):
                normalized_candidates[str(key)] = [item for item in value if isinstance(item, dict)]
        monkeypatch.setattr(chat_tools, "retrieve_candidates", _mock_candidates_factory(normalized_candidates))

    captured_token: str | None = None
    for turn in scenario["turns"]:
        assert isinstance(turn, dict)
        advance_sec = int(turn.get("advance_sec") or 0)
        if advance_sec > 0:
            time_state["now"] += advance_sec

        raw_query = str(turn.get("query") or "")
        if "{{token}}" in raw_query:
            assert captured_token, f"missing token for scenario={scenario['id']}"
            query = raw_query.replace("{{token}}", captured_token)
        else:
            query = raw_query
        user_id = turn.get("user_id")
        client_payload: dict[str, Any] = {"locale": "ko-KR"}
        if isinstance(user_id, str) and user_id.strip():
            client_payload["user_id"] = user_id.strip()
        payload = {
            "session_id": session_id,
            "message": {"role": "user", "content": query},
            "client": client_payload,
        }
        response = asyncio.run(chat_tools.run_tool_chat(payload, "trace_regression", f"req_{scenario['id']}"))
        assert isinstance(response, dict), f"expected response dict for scenario={scenario['id']}"

        expected = turn.get("expected")
        if isinstance(expected, dict):
            expected_status = expected.get("status")
            expected_reason = expected.get("reason_code")
            if isinstance(expected_status, str):
                assert response.get("status") == expected_status
            if isinstance(expected_reason, str):
                assert response.get("reason_code") == expected_reason

        content = str((response.get("answer") or {}).get("content") or "")
        if turn.get("capture_token") is True:
            token = _extract_confirmation_token(content)
            assert token, f"token missing for scenario={scenario['id']}"
            captured_token = token

        expected_workflow_state = turn.get("expected_workflow_state")
        if isinstance(expected_workflow_state, str):
            workflow = chat_tools._load_workflow(session_id)
            assert isinstance(workflow, dict), f"workflow missing for scenario={scenario['id']}"
            assert chat_tools._workflow_fsm_state(workflow) == expected_workflow_state

        if turn.get("expect_no_pending_workflow") is True:
            workflow = chat_tools._load_workflow(session_id)
            state = chat_tools._workflow_fsm_state(workflow) if isinstance(workflow, dict) else "INIT"
            assert state not in chat_tools._WORKFLOW_PENDING_STATES

        # Claim guard regression: never allow "완료" claims without evidence.
        has_success_word = "완료" in content
        sources = response.get("sources") if isinstance(response.get("sources"), list) else []
        citations = response.get("citations") if isinstance(response.get("citations"), list) else []
        if has_success_word and response.get("status") == "ok":
            assert sources and citations, f"success claim without evidence in scenario={scenario['id']}"
