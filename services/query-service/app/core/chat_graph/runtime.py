from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.core.chat_graph.state import (
    ChatGraphState,
    ChatGraphStateValidationError,
    build_chat_graph_state,
    validate_chat_graph_state,
)


LegacyExecutor = Callable[[dict[str, Any], str, str], Awaitable[dict[str, Any]]]
NodeFn = Callable[[ChatGraphState], Awaitable[ChatGraphState]]


@dataclass(frozen=True)
class ChatGraphNodeContract:
    name: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]


@dataclass
class ChatGraphRuntimeResult:
    state: ChatGraphState
    response: dict[str, Any]
    stage: str


CHAT_GRAPH_NODE_CONTRACTS: dict[str, ChatGraphNodeContract] = {
    "load_state": ChatGraphNodeContract(
        name="load_state",
        required_inputs=("trace_id", "request_id", "session_id", "query"),
        required_outputs=("session", "state_version"),
    ),
    "understand": ChatGraphNodeContract(
        name="understand",
        required_inputs=("query",),
        required_outputs=("intent",),
    ),
    "policy_decide": ChatGraphNodeContract(
        name="policy_decide",
        required_inputs=("intent", "query"),
        required_outputs=("route",),
    ),
    "execute": ChatGraphNodeContract(
        name="execute",
        required_inputs=("route",),
        required_outputs=("response", "reason_code", "route"),
    ),
    "compose": ChatGraphNodeContract(
        name="compose",
        required_inputs=("response",),
        required_outputs=("response",),
    ),
    "verify": ChatGraphNodeContract(
        name="verify",
        required_inputs=("response",),
        required_outputs=("response", "reason_code"),
    ),
    "persist": ChatGraphNodeContract(
        name="persist",
        required_inputs=("response",),
        required_outputs=("state_version", "session"),
    ),
}


async def run_chat_graph(
    request: dict[str, Any],
    trace_id: str,
    request_id: str,
    *,
    legacy_executor: LegacyExecutor,
) -> ChatGraphRuntimeResult:
    session_id = _resolve_session_id(request)
    query = _extract_query(request)
    user_id = _extract_user_id(request)

    state = build_chat_graph_state(
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
        query=query,
        user_id=user_id,
    )

    try:
        state = await _run_node("load_state", state, _load_state_node)
        state = await _run_node("understand", state, _understand_node)
        state = await _run_node("policy_decide", state, _policy_decide_node)
        state = await _run_node("execute", state, _execute_node_factory(request, trace_id, request_id, legacy_executor))
        state = await _run_node("compose", state, _compose_node)
        state = await _run_node("verify", state, _verify_node)
        state = await _run_node("persist", state, _persist_node)
    except ChatGraphStateValidationError as exc:
        handled = _error_handler_state(
            state,
            trace_id=trace_id,
            request_id=request_id,
            stage=exc.stage,
            reason_code=exc.reason_code,
        )
        return ChatGraphRuntimeResult(state=handled, response=_state_response(handled), stage="error_handler")
    except Exception:
        handled = _error_handler_state(
            state,
            trace_id=trace_id,
            request_id=request_id,
            stage="runtime",
            reason_code="CHAT_GRAPH_RUNTIME_ERROR",
        )
        return ChatGraphRuntimeResult(state=handled, response=_state_response(handled), stage="error_handler")

    return ChatGraphRuntimeResult(state=state, response=_state_response(state), stage="persist")


async def _run_node(name: str, state: ChatGraphState, fn: NodeFn) -> ChatGraphState:
    contract = CHAT_GRAPH_NODE_CONTRACTS[name]
    validated = validate_chat_graph_state(state, stage=f"{name}:input")
    _assert_contract_fields(validated, contract.required_inputs, stage=f"{name}:input")
    updated = await fn(validated)
    validated_out = validate_chat_graph_state(updated, stage=f"{name}:output")
    _assert_contract_fields(validated_out, contract.required_outputs, stage=f"{name}:output")
    return validated_out


def _assert_contract_fields(state: ChatGraphState, fields: tuple[str, ...], *, stage: str) -> None:
    issues: list[str] = []
    for field in fields:
        value = state.get(field)
        if value is None:
            issues.append(f"missing required contract field: {field}")
    if issues:
        raise ChatGraphStateValidationError(stage, issues)


async def _load_state_node(state: ChatGraphState) -> ChatGraphState:
    state["session"]["recommended_message"] = state["session"].get("recommended_message") or "현재 챗봇 세션 상태는 정상입니다."
    return state


async def _understand_node(state: ChatGraphState) -> ChatGraphState:
    q = (state.get("query") or "").lower()
    intent = "GENERAL"
    if any(keyword in q for keyword in ("환불", "취소", "refund", "cancel")):
        intent = "REFUND"
    elif any(keyword in q for keyword in ("배송", "shipping", "tracking")):
        intent = "SHIPPING"
    elif any(keyword in q for keyword in ("주문", "결제", "order", "payment")):
        intent = "ORDER"
    elif any(keyword in q for keyword in ("추천", "recommend", "similar")):
        intent = "RECOMMEND"
    state["intent"] = intent
    return state


async def _policy_decide_node(state: ChatGraphState) -> ChatGraphState:
    query = (state.get("query") or "").strip()
    pending_action = state.get("pending_action")

    if not query:
        state["route"] = "ASK"
        state["reason_code"] = "NO_MESSAGES"
        return state

    if isinstance(pending_action, dict):
        action_state = str(pending_action.get("state") or "").upper()
        if action_state in {"AWAITING_CONFIRMATION", "CONFIRMED"}:
            state["route"] = "CONFIRM"
            state["reason_code"] = "CONFIRMATION_REQUIRED"
            return state

    state["route"] = "EXECUTE"
    if not state.get("reason_code"):
        state["reason_code"] = "OK"
    return state


def _execute_node_factory(
    request: dict[str, Any],
    trace_id: str,
    request_id: str,
    legacy_executor: LegacyExecutor,
) -> NodeFn:
    async def _execute_node(state: ChatGraphState) -> ChatGraphState:
        route = state.get("route")
        if route == "ASK":
            fallback = _fallback_response(trace_id, request_id, reason_code="NO_MESSAGES", next_action="PROVIDE_REQUIRED_INFO")
            state["response"] = _state_response_payload(fallback)
            state["route"] = "FALLBACK"
            state["reason_code"] = "NO_MESSAGES"
            return state

        try:
            response = await legacy_executor(request, trace_id, request_id)
        except Exception:
            fallback = _fallback_response(trace_id, request_id, reason_code="PROVIDER_TIMEOUT", next_action="RETRY")
            state["response"] = _state_response_payload(fallback)
            state["tool_result"] = {
                "status": "error",
                "reason_code": "PROVIDER_TIMEOUT",
                "source": "legacy_executor",
                "data": {},
            }
            state["route"] = "FALLBACK"
            state["reason_code"] = "PROVIDER_TIMEOUT"
            return state

        if not isinstance(response, dict):
            fallback = _fallback_response(trace_id, request_id, reason_code="CHAT_GRAPH_EXECUTION_ERROR", next_action="RETRY")
            state["response"] = _state_response_payload(fallback)
            state["tool_result"] = {
                "status": "error",
                "reason_code": "CHAT_GRAPH_EXECUTION_ERROR",
                "source": "legacy_executor",
                "data": {},
            }
            state["route"] = "FALLBACK"
            state["reason_code"] = "CHAT_GRAPH_EXECUTION_ERROR"
            return state

        state["response"] = _state_response_payload(response)
        state["tool_result"] = {
            "status": "ok",
            "reason_code": str(response.get("reason_code") or "OK"),
            "source": "legacy_executor",
            "data": {"status": response.get("status")},
        }
        status = str(response.get("status") or "ok")
        state["route"] = "ANSWER" if status == "ok" else "FALLBACK"
        state["reason_code"] = str(response.get("reason_code") or ("OK" if status == "ok" else "UNKNOWN"))
        return state

    return _execute_node


async def _compose_node(state: ChatGraphState) -> ChatGraphState:
    response = state.get("response")
    if not isinstance(response, dict):
        return state

    answer = response.get("answer")
    if not isinstance(answer, dict):
        response["answer"] = {"role": "assistant", "content": ""}
    else:
        response["answer"] = {
            "role": str(answer.get("role") or "assistant"),
            "content": str(answer.get("content") or ""),
        }
    state["response"] = response
    return state


async def _verify_node(state: ChatGraphState) -> ChatGraphState:
    response = state.get("response")
    if not isinstance(response, dict):
        state["response"] = _state_response_payload(
            _fallback_response(
                state["trace_id"],
                state["request_id"],
                reason_code="CHAT_GRAPH_RESPONSE_MISSING",
                next_action="RETRY",
            )
        )
        state["route"] = "FALLBACK"
        state["reason_code"] = "CHAT_GRAPH_RESPONSE_MISSING"
        return state

    status = str(response.get("status") or "")
    answer = response.get("answer")
    if status == "ok" and (not isinstance(answer, dict) or not str(answer.get("content") or "").strip()):
        state["response"] = _state_response_payload(
            _fallback_response(
                state["trace_id"],
                state["request_id"],
                reason_code="OUTPUT_GUARD_EMPTY_ANSWER",
                next_action="RETRY",
            )
        )
        state["route"] = "FALLBACK"
        state["reason_code"] = "OUTPUT_GUARD_EMPTY_ANSWER"
        return state

    if not state.get("reason_code"):
        state["reason_code"] = str(response.get("reason_code") or "OK")
    return state


async def _persist_node(state: ChatGraphState) -> ChatGraphState:
    state["state_version"] = int(state.get("state_version") or 1) + 1
    response = state.get("response")
    if isinstance(response, dict):
        fallback_count = response.get("fallback_count")
        if isinstance(fallback_count, int) and fallback_count >= 0:
            state["session"]["fallback_count"] = fallback_count
        escalated = response.get("escalated")
        if isinstance(escalated, bool):
            state["session"]["escalation_ready"] = escalated
        next_action = response.get("next_action")
        if isinstance(next_action, str) and next_action.strip():
            state["session"]["recommended_action"] = next_action
    return state


def _error_handler_state(
    state: ChatGraphState,
    *,
    trace_id: str,
    request_id: str,
    stage: str,
    reason_code: str,
) -> ChatGraphState:
    fallback = _fallback_response(trace_id, request_id, reason_code=reason_code, next_action="OPEN_SUPPORT_TICKET")
    state.update(
        {
            "trace_id": trace_id,
            "request_id": request_id,
            "route": "FALLBACK",
            "reason_code": reason_code,
            "response": _state_response_payload(fallback),
            "tool_result": {
                "status": "error",
                "reason_code": reason_code,
                "source": "error_handler",
                "data": {"stage": stage},
            },
        }
    )
    return state


def _state_response_payload(response: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": str(response.get("status") or "insufficient_evidence"),
        "reason_code": str(response.get("reason_code") or "UNKNOWN"),
        "recoverable": bool(response.get("recoverable", True)),
        "next_action": str(response.get("next_action") or "RETRY"),
        "retry_after_ms": response.get("retry_after_ms"),
        "answer": dict(response.get("answer") or {"role": "assistant", "content": ""}),
        "citations": list(response.get("citations") or []),
        "sources": list(response.get("sources") or []),
        "fallback_count": int(response.get("fallback_count") or 0),
        "escalated": bool(response.get("escalated", False)),
    }
    return payload


def _state_response(state: ChatGraphState) -> dict[str, Any]:
    response = dict(state.get("response") or {})
    return {
        "version": "v1",
        "trace_id": state.get("trace_id"),
        "request_id": state.get("request_id"),
        "status": str(response.get("status") or "insufficient_evidence"),
        "reason_code": str(response.get("reason_code") or state.get("reason_code") or "UNKNOWN"),
        "recoverable": bool(response.get("recoverable", True)),
        "next_action": str(response.get("next_action") or "RETRY"),
        "retry_after_ms": response.get("retry_after_ms"),
        "answer": dict(response.get("answer") or {"role": "assistant", "content": ""}),
        "sources": list(response.get("sources") or []),
        "citations": list(response.get("citations") or []),
        "fallback_count": int(response.get("fallback_count") or 0),
        "escalated": bool(response.get("escalated", False)),
    }


def _fallback_response(trace_id: str, request_id: str, *, reason_code: str, next_action: str) -> dict[str, Any]:
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "insufficient_evidence",
        "reason_code": reason_code,
        "recoverable": True,
        "next_action": next_action,
        "retry_after_ms": 3000,
        "answer": {
            "role": "assistant",
            "content": "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        },
        "sources": [],
        "citations": [],
        "fallback_count": 0,
        "escalated": False,
    }


def _extract_query(request: dict[str, Any]) -> str:
    message = request.get("message") if isinstance(request.get("message"), dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, str):
        return content
    return ""


def _extract_user_id(request: dict[str, Any]) -> str | None:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    user_id = client.get("user_id") if isinstance(client, dict) else None
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    return None


def _resolve_session_id(request: dict[str, Any]) -> str:
    raw = request.get("session_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    user_id = _extract_user_id(request)
    if user_id:
        return f"u:{user_id}:default"
    return "anon:default"
