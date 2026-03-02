from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping
import hashlib
import time

from app.core.chat_graph.state import (
    ChatGraphState,
    ChatGraphStateValidationError,
    build_chat_graph_state,
    validate_chat_graph_state,
)
from app.core.chat_graph.confirm_fsm import (
    evaluate_confirmation,
    init_pending_action,
    load_pending_action,
    mark_execution_result,
    mark_execution_start,
    save_pending_action,
)
from app.core.chat_graph.authz_gate import (
    append_authz_audit,
    authorize_request,
    build_action_protocol,
)
from app.core.chat_graph.replay_store import (
    append_checkpoint,
    finish_run,
    start_run_record,
)
from app.core.chat_graph.reason_taxonomy import (
    DEFAULT_UNSPECIFIED_REASON_CODE,
    normalize_reason_code,
    record_reason_code_event,
)
from app.core.chat_graph.langsmith_trace import (
    TraceDecision,
    emit_trace_event,
    resolve_trace_decision,
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
    run_id: str = ""


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
    "authz_gate": ChatGraphNodeContract(
        name="authz_gate",
        required_inputs=("route", "session_id"),
        required_outputs=("route", "reason_code"),
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
    run_id: str | None = None,
    record_run: bool = False,
) -> ChatGraphRuntimeResult:
    session_id = _resolve_session_id(request)
    query = _extract_query(request)
    user_id = _extract_user_id(request)
    resolved_run_id = run_id or _build_run_id(trace_id, request_id, session_id)

    state = build_chat_graph_state(
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
        query=query,
        user_id=user_id,
    )
    trace_context = _build_trace_context(request, session_id=session_id, user_id=user_id)
    trace_decision = resolve_trace_decision(trace_id=trace_id, session_id=session_id, context=trace_context)
    await _safe_emit_trace_event(
        decision=trace_decision,
        run_id=resolved_run_id,
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
        event_type="run_start",
        node=None,
        metadata=_trace_metadata(state, trace_context),
        payload={"query": query},
    )
    if record_run:
        start_run_record(
            run_id=resolved_run_id,
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            request_payload=request,
            replay_payload={
                "trace_id": trace_id,
                "request_id": request_id,
                "session_id": session_id,
                "input": request,
                "policy_decision": {},
                "tool_stub_seed": None,
            },
        )

    try:
        state = await _run_node("load_state", state, _load_state_node)
        _record_state_reason_code(state, source="load_state")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="load_state",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "load_state", state)
        state = await _run_node("understand", state, _understand_node)
        _record_state_reason_code(state, source="understand")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="understand",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "understand", state)
        state = await _run_node("policy_decide", state, _policy_decide_node)
        _record_state_reason_code(state, source="policy_decide")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="policy_decide",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "policy_decide", state)
        state = await _run_node("authz_gate", state, _authz_gate_node_factory(request, trace_id, request_id))
        _record_state_reason_code(state, source="authz_gate")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="authz_gate",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "authz_gate", state)
        state = await _run_node("execute", state, _execute_node_factory(request, trace_id, request_id, legacy_executor))
        _record_state_reason_code(state, source="execute")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="execute",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "execute", state)
        state = await _run_node("compose", state, _compose_node)
        _record_state_reason_code(state, source="compose")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="compose",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "compose", state)
        state = await _run_node("verify", state, _verify_node)
        _record_state_reason_code(state, source="verify")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="verify",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "verify", state)
        state = await _run_node("persist", state, _persist_node)
        _record_state_reason_code(state, source="persist")
        await _emit_node_trace(
            trace_decision=trace_decision,
            run_id=resolved_run_id,
            node="persist",
            state=state,
            trace_context=trace_context,
        )
        if record_run:
            append_checkpoint(resolved_run_id, "persist", state)
    except ChatGraphStateValidationError as exc:
        handled = _error_handler_state(
            state,
            trace_id=trace_id,
            request_id=request_id,
            stage=exc.stage,
            reason_code=exc.reason_code,
        )
        _record_state_reason_code(handled, source="error_handler")
        await _safe_emit_trace_event(
            decision=trace_decision,
            run_id=resolved_run_id,
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            event_type="run_error",
            node=exc.stage,
            metadata=_trace_metadata(handled, trace_context),
            payload={"stage": exc.stage, "reason_code": exc.reason_code},
        )
        error_response = _state_response(handled)
        if record_run:
            finish_run(
                resolved_run_id,
                stage="error_handler",
                response=error_response,
                stub_response=None,
            )
        return ChatGraphRuntimeResult(state=handled, response=error_response, stage="error_handler", run_id=resolved_run_id)
    except Exception:
        handled = _error_handler_state(
            state,
            trace_id=trace_id,
            request_id=request_id,
            stage="runtime",
            reason_code="CHAT_GRAPH_RUNTIME_ERROR",
        )
        _record_state_reason_code(handled, source="error_handler")
        await _safe_emit_trace_event(
            decision=trace_decision,
            run_id=resolved_run_id,
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            event_type="run_error",
            node="runtime",
            metadata=_trace_metadata(handled, trace_context),
            payload={"stage": "runtime", "reason_code": "CHAT_GRAPH_RUNTIME_ERROR"},
        )
        error_response = _state_response(handled)
        if record_run:
            finish_run(
                resolved_run_id,
                stage="error_handler",
                response=error_response,
                stub_response=None,
            )
        return ChatGraphRuntimeResult(state=handled, response=error_response, stage="error_handler", run_id=resolved_run_id)

    final_response = _state_response(state)
    _record_response_reason_code(
        state,
        response=final_response,
        source="response",
    )
    await _safe_emit_trace_event(
        decision=trace_decision,
        run_id=resolved_run_id,
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
        event_type="run_end",
        node=None,
        metadata=_trace_metadata(state, trace_context),
        payload={
            "status": final_response.get("status"),
            "reason_code": final_response.get("reason_code"),
            "next_action": final_response.get("next_action"),
            "answer": final_response.get("answer", {}).get("content")
            if isinstance(final_response.get("answer"), dict)
            else "",
        },
    )
    if record_run:
        tool_result = state.get("tool_result") if isinstance(state.get("tool_result"), dict) else {}
        data = tool_result.get("data") if isinstance(tool_result.get("data"), dict) else {}
        stub_response = data.get("stub_response") if isinstance(data.get("stub_response"), dict) else final_response
        finish_run(
            resolved_run_id,
            stage="persist",
            response=final_response,
            stub_response=stub_response,
        )
    return ChatGraphRuntimeResult(state=state, response=final_response, stage="persist", run_id=resolved_run_id)


def _record_state_reason_code(state: ChatGraphState, *, source: str) -> None:
    reason_code = state.get("reason_code")
    if not isinstance(reason_code, str) or not reason_code.strip():
        return
    normalized = normalize_reason_code(reason_code, source=source)
    state["reason_code"] = normalized
    record_reason_code_event(
        session_id=str(state.get("session_id") or "anon:default"),
        trace_id=str(state.get("trace_id") or ""),
        request_id=str(state.get("request_id") or ""),
        source=source,
        reason_code=reason_code,
    )


def _record_response_reason_code(
    state: ChatGraphState,
    *,
    response: dict[str, Any],
    source: str,
) -> None:
    reason_code = str(response.get("reason_code") or state.get("reason_code") or DEFAULT_UNSPECIFIED_REASON_CODE)
    normalized = normalize_reason_code(reason_code, source=source)
    response["reason_code"] = normalized
    state["reason_code"] = normalized
    record_reason_code_event(
        session_id=str(state.get("session_id") or "anon:default"),
        trace_id=str(state.get("trace_id") or ""),
        request_id=str(state.get("request_id") or ""),
        source=source,
        reason_code=reason_code,
    )


def _build_trace_context(
    request: dict[str, Any],
    *,
    session_id: str,
    user_id: str | None,
) -> dict[str, str]:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    tenant_id = str(client.get("tenant_id") or "")
    channel = str(client.get("channel") or "web")
    return {
        "tenant_id": tenant_id,
        "channel": channel,
        "user_id": str(user_id or ""),
        "session_id": session_id,
    }


def _trace_metadata(state: ChatGraphState, context: Mapping[str, str]) -> dict[str, Any]:
    return {
        "trace_id": str(state.get("trace_id") or ""),
        "request_id": str(state.get("request_id") or ""),
        "session_id": str(state.get("session_id") or ""),
        "route": str(state.get("route") or ""),
        "reason_code": str(state.get("reason_code") or ""),
        "state_version": int(state.get("state_version") or 0),
        "tenant_id": str(context.get("tenant_id") or ""),
        "channel": str(context.get("channel") or ""),
        "user_id": str(context.get("user_id") or ""),
    }


async def _emit_node_trace(
    *,
    trace_decision: TraceDecision,
    run_id: str,
    node: str,
    state: ChatGraphState,
    trace_context: Mapping[str, str],
) -> None:
    response = state.get("response") if isinstance(state.get("response"), dict) else {}
    await _safe_emit_trace_event(
        decision=trace_decision,
        run_id=run_id,
        trace_id=str(state.get("trace_id") or ""),
        request_id=str(state.get("request_id") or ""),
        session_id=str(state.get("session_id") or ""),
        event_type="node",
        node=node,
        metadata=_trace_metadata(state, trace_context),
        payload={
            "route": str(state.get("route") or ""),
            "reason_code": str(state.get("reason_code") or ""),
            "response_status": str(response.get("status") or ""),
        },
    )


async def _safe_emit_trace_event(
    *,
    decision: TraceDecision,
    run_id: str,
    trace_id: str,
    request_id: str,
    session_id: str,
    event_type: str,
    node: str | None,
    metadata: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> None:
    try:
        await emit_trace_event(
            decision=decision,
            run_id=run_id,
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            event_type=event_type,
            node=node,
            metadata=metadata,
            payload=payload,
        )
    except Exception:
        # Trace export must never block runtime path.
        return


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


def _build_run_id(trace_id: str, request_id: str, session_id: str) -> str:
    seed = f"{trace_id}:{request_id}:{session_id}:{int(time.time() * 1000)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"run_{digest}"


async def _load_state_node(state: ChatGraphState) -> ChatGraphState:
    state["session"]["recommended_message"] = state["session"].get("recommended_message") or "현재 챗봇 세션 상태는 정상입니다."
    pending_action = load_pending_action(state["session_id"])
    if isinstance(pending_action, dict):
        state["pending_action"] = pending_action
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

    if pending_action is not None:
        state["route"] = "CONFIRM"
        state["reason_code"] = "CONFIRMATION_REQUIRED"
        return state

    if _requires_confirmation(state.get("intent"), query):
        action_type = _derive_action_type(state.get("intent"), query)
        pending = init_pending_action(
            state["session_id"],
            action_type=action_type,
            query=query,
            trace_id=state["trace_id"],
            request_id=state["request_id"],
        )
        pending["action_protocol"] = build_action_protocol(
            action_type=action_type,
            args=dict(pending.get("payload") or {}),
            idempotency_key=str(pending.get("idempotency_key") or ""),
            risk_level="WRITE_SENSITIVE",
            requires_confirmation=True,
        )
        save_pending_action(state["session_id"], pending)
        state["pending_action"] = pending
        state["route"] = "CONFIRM"
        state["reason_code"] = "CONFIRMATION_REQUIRED"
        return state

    state["route"] = "EXECUTE"
    if not state.get("reason_code"):
        state["reason_code"] = "OK"
    return state


def _requires_confirmation(intent: str | None, query: str) -> bool:
    normalized = (query or "").lower()
    if not normalized:
        return False
    if any(keyword in normalized for keyword in ("중단", "abort")):
        return False
    if any(keyword in normalized for keyword in ("확인", "confirm")):
        return False
    write_keywords = ("취소", "환불", "refund", "cancel", "주소 변경", "address change")
    if any(keyword in normalized for keyword in write_keywords):
        return True
    return intent in {"REFUND", "ORDER"} and any(keyword in normalized for keyword in ("요청", "처리", "진행"))


def _derive_action_type(intent: str | None, query: str) -> str:
    normalized = (query or "").lower()
    if any(keyword in normalized for keyword in ("환불", "refund")):
        return "REFUND_REQUEST"
    if any(keyword in normalized for keyword in ("취소", "cancel")):
        return "ORDER_CANCEL"
    if any(keyword in normalized for keyword in ("주소 변경", "address change")):
        return "ADDRESS_CHANGE"
    if intent == "ORDER":
        return "ORDER_UPDATE"
    return "SENSITIVE_ACTION"


def _authz_gate_node_factory(request: dict[str, Any], trace_id: str, request_id: str) -> NodeFn:
    async def _authz_gate_node(state: ChatGraphState) -> ChatGraphState:
        route = str(state.get("route") or "")
        if route not in {"CONFIRM", "EXECUTE"}:
            if not state.get("reason_code"):
                state["reason_code"] = "OK"
            return state

        pending_action = state.get("pending_action")
        if route == "EXECUTE" and not isinstance(pending_action, dict):
            if not state.get("reason_code"):
                state["reason_code"] = "OK"
            return state

        if not isinstance(pending_action, dict):
            state["route"] = "FALLBACK"
            state["reason_code"] = "INVALID_WORKFLOW_STATE"
            state["response"] = _state_response_payload(
                _deny_response(
                    trace_id,
                    request_id,
                    reason_code="INVALID_WORKFLOW_STATE",
                    next_action="OPEN_SUPPORT_TICKET",
                    message="민감 액션 상태가 유효하지 않습니다.",
                )
            )
            return state

        action_protocol = pending_action.get("action_protocol")
        if not isinstance(action_protocol, dict):
            action_protocol = build_action_protocol(
                action_type=str(pending_action.get("action_type") or "SENSITIVE_ACTION"),
                args=dict(pending_action.get("payload") or {}),
                idempotency_key=str(pending_action.get("idempotency_key") or ""),
                risk_level="WRITE_SENSITIVE",
                requires_confirmation=bool(pending_action.get("requires_confirmation", True)),
            )
            pending_action["action_protocol"] = action_protocol
            state["pending_action"] = pending_action
            save_pending_action(state["session_id"], pending_action)

        decision = authorize_request(request, action_protocol)
        actor, target = _authz_actor_target(request, action_protocol)
        append_authz_audit(
            state["session_id"],
            trace_id=trace_id,
            request_id=request_id,
            actor=actor,
            target=target,
            decision=decision,
        )
        if not decision.allowed:
            state["route"] = "FALLBACK"
            state["reason_code"] = decision.reason_code
            state["response"] = _state_response_payload(
                _deny_response(
                    trace_id,
                    request_id,
                    reason_code=decision.reason_code,
                    next_action=decision.next_action,
                    message=decision.message,
                )
            )
            return state

        if not state.get("reason_code"):
            state["reason_code"] = "OK"
        return state

    return _authz_gate_node


def _authz_actor_target(request: dict[str, Any], action_protocol: dict[str, Any]) -> tuple[str, str]:
    client = request.get("client") if isinstance(request.get("client"), dict) else {}
    actor = str(client.get("user_id") or "-")
    args = action_protocol.get("args") if isinstance(action_protocol.get("args"), dict) else {}
    target = str(args.get("target_user_id") or actor or "-")
    return actor, target


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
        if route == "FALLBACK":
            if isinstance(state.get("response"), dict):
                return state
            fallback = _fallback_response(
                trace_id,
                request_id,
                reason_code=str(state.get("reason_code") or "CHAT_GRAPH_EXECUTION_BLOCKED"),
                next_action="RETRY",
            )
            state["response"] = _state_response_payload(fallback)
            state["route"] = "FALLBACK"
            state["reason_code"] = str(state.get("reason_code") or "CHAT_GRAPH_EXECUTION_BLOCKED")
            return state

        pending_action = state.get("pending_action") if isinstance(state.get("pending_action"), dict) else None
        if route == "CONFIRM":
            if pending_action is None:
                fallback = _fallback_response(
                    trace_id,
                    request_id,
                    reason_code="INVALID_WORKFLOW_STATE",
                    next_action="OPEN_SUPPORT_TICKET",
                )
                state["response"] = _state_response_payload(fallback)
                state["route"] = "FALLBACK"
                state["reason_code"] = "INVALID_WORKFLOW_STATE"
                return state

            decision = evaluate_confirmation(
                state["session_id"],
                pending_action,
                query=state.get("query") or "",
                trace_id=trace_id,
                request_id=request_id,
            )
            state["pending_action"] = decision.pending_action
            state["reason_code"] = decision.reason_code
            if not decision.allow_execute:
                state["response"] = _state_response_payload(
                    _confirmation_response(
                        trace_id,
                        request_id,
                        reason_code=decision.reason_code,
                        message=decision.user_message,
                        next_action=decision.next_action,
                        retry_after_ms=decision.retry_after_ms,
                    )
                )
                if decision.reason_code in {"CONFIRMATION_REQUIRED", "CONFIRMATION_TOKEN_MISMATCH"}:
                    state["route"] = "CONFIRM"
                else:
                    state["route"] = "FALLBACK"
                return state

            if isinstance(state.get("pending_action"), dict):
                state["pending_action"] = mark_execution_start(
                    state["session_id"],
                    state["pending_action"],
                    trace_id=trace_id,
                    request_id=request_id,
                )

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
            if isinstance(state.get("pending_action"), dict):
                updated = mark_execution_result(
                    state["session_id"],
                    state["pending_action"],
                    trace_id=trace_id,
                    request_id=request_id,
                    success=False,
                    final_reason_code="PROVIDER_TIMEOUT",
                    final_retryable=True,
                )
                state["pending_action"] = updated
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
            if isinstance(state.get("pending_action"), dict):
                updated = mark_execution_result(
                    state["session_id"],
                    state["pending_action"],
                    trace_id=trace_id,
                    request_id=request_id,
                    success=False,
                    final_reason_code="CHAT_GRAPH_EXECUTION_ERROR",
                    final_retryable=True,
                )
                state["pending_action"] = updated
            return state

        state["response"] = _state_response_payload(response)
        state["tool_result"] = {
            "status": "ok",
            "reason_code": str(response.get("reason_code") or "OK"),
            "source": "legacy_executor",
            "data": {"status": response.get("status"), "stub_response": response},
        }
        status = str(response.get("status") or "ok")
        state["route"] = "ANSWER" if status == "ok" else "FALLBACK"
        default_reason = "OK" if status == "ok" else DEFAULT_UNSPECIFIED_REASON_CODE
        state["reason_code"] = str(response.get("reason_code") or default_reason)
        if isinstance(state.get("pending_action"), dict):
            reason_code = str(response.get("reason_code") or default_reason)
            recoverable = bool(response.get("recoverable", True))
            updated = mark_execution_result(
                state["session_id"],
                state["pending_action"],
                trace_id=trace_id,
                request_id=request_id,
                success=status == "ok",
                final_reason_code=reason_code,
                final_retryable=recoverable,
            )
            if str(updated.get("state") or "") == "EXECUTED":
                state["pending_action"] = None
            else:
                state["pending_action"] = updated
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
    status = str(response.get("status") or "insufficient_evidence")
    reason_default = "OK" if status == "ok" else DEFAULT_UNSPECIFIED_REASON_CODE
    reason_code = normalize_reason_code(
        response.get("reason_code") or reason_default,
        source="response",
    )
    payload: dict[str, Any] = {
        "status": status,
        "reason_code": reason_code,
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
    status = str(response.get("status") or "insufficient_evidence")
    reason_default = "OK" if status == "ok" else DEFAULT_UNSPECIFIED_REASON_CODE
    reason_code = normalize_reason_code(
        response.get("reason_code") or state.get("reason_code") or reason_default,
        source="response",
    )
    return {
        "version": "v1",
        "trace_id": state.get("trace_id"),
        "request_id": state.get("request_id"),
        "status": status,
        "reason_code": reason_code,
        "recoverable": bool(response.get("recoverable", True)),
        "next_action": str(response.get("next_action") or "RETRY"),
        "retry_after_ms": response.get("retry_after_ms"),
        "answer": dict(response.get("answer") or {"role": "assistant", "content": ""}),
        "sources": list(response.get("sources") or []),
        "citations": list(response.get("citations") or []),
        "fallback_count": int(response.get("fallback_count") or 0),
        "escalated": bool(response.get("escalated", False)),
    }


def _confirmation_response(
    trace_id: str,
    request_id: str,
    *,
    reason_code: str,
    message: str,
    next_action: str,
    retry_after_ms: int | None,
) -> dict[str, Any]:
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "pending_confirmation" if reason_code in {"CONFIRMATION_REQUIRED", "CONFIRMATION_TOKEN_MISMATCH"} else "insufficient_evidence",
        "reason_code": reason_code,
        "recoverable": True,
        "next_action": next_action,
        "retry_after_ms": retry_after_ms,
        "answer": {"role": "assistant", "content": message},
        "sources": [],
        "citations": [],
        "fallback_count": 0,
        "escalated": False,
    }


def _deny_response(
    trace_id: str,
    request_id: str,
    *,
    reason_code: str,
    next_action: str,
    message: str,
) -> dict[str, Any]:
    return {
        "version": "v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "status": "insufficient_evidence",
        "reason_code": reason_code,
        "recoverable": True,
        "next_action": next_action,
        "retry_after_ms": None,
        "answer": {"role": "assistant", "content": message},
        "sources": [],
        "citations": [],
        "fallback_count": 0,
        "escalated": False,
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
