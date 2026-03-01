from app.core.chat_policy_engine import build_understanding
from app.core.chat_policy_engine import decide_route
from app.core.chat_policy_engine import ROUTE_ANSWER
from app.core.chat_policy_engine import ROUTE_ASK
from app.core.chat_policy_engine import ROUTE_CONFIRM
from app.core.chat_policy_engine import ROUTE_OPTIONS


def test_policy_engine_routes_write_intent_to_confirm_when_slots_present():
    understanding = build_understanding(
        query="주문 12 취소해줘",
        intent="ORDER_CANCEL",
        slots={"order_ref": {"order_id": 12, "order_no": None}},
    )

    decision = decide_route(
        understanding,
        has_user=True,
        has_pending_action=False,
        pending_state=None,
        is_reference_query=False,
        has_selection_state=False,
    )

    assert decision.route == ROUTE_CONFIRM
    assert decision.reason_code == "ROUTE:CONFIRM:ORDER_CANCEL"


def test_policy_engine_blocks_missing_slot_for_sensitive_write():
    understanding = build_understanding(
        query="환불 신청해줘",
        intent="REFUND_CREATE",
        slots={"order_ref": None},
    )

    decision = decide_route(
        understanding,
        has_user=True,
        has_pending_action=False,
        pending_state=None,
        is_reference_query=False,
        has_selection_state=False,
    )

    assert decision.route == ROUTE_ASK
    assert decision.reason_code == "NEED_SLOT:ORDER_REF"


def test_policy_engine_requires_auth_for_lookup():
    understanding = build_understanding(
        query="주문 상태 알려줘",
        intent="ORDER_LOOKUP",
        slots={"order_ref": {"order_id": 12, "order_no": None}},
    )

    decision = decide_route(
        understanding,
        has_user=False,
        has_pending_action=False,
        pending_state=None,
        is_reference_query=False,
        has_selection_state=False,
    )

    assert decision.route == ROUTE_ASK
    assert decision.reason_code == "NEED_AUTH:USER_LOGIN"


def test_policy_engine_routes_pending_action_to_confirm():
    understanding = build_understanding(
        query="확인 ABCDEF",
        intent="NONE",
        slots={},
    )

    decision = decide_route(
        understanding,
        has_user=True,
        has_pending_action=True,
        pending_state="AWAITING_CONFIRMATION",
        is_reference_query=False,
        has_selection_state=False,
    )

    assert decision.route == ROUTE_CONFIRM
    assert decision.reason_code == "ROUTE:CONFIRM:PENDING_ACTION"


def test_policy_engine_routes_reference_without_selection_to_options():
    understanding = build_understanding(
        query="그거 추천해줘",
        intent="NONE",
        slots={},
    )

    decision = decide_route(
        understanding,
        has_user=False,
        has_pending_action=False,
        pending_state=None,
        is_reference_query=True,
        has_selection_state=False,
    )

    assert decision.route == ROUTE_OPTIONS
    assert decision.reason_code == "ROUTE:OPTIONS:DISAMBIGUATE:BOOK"


def test_policy_engine_routes_policy_intent_to_answer_deterministically():
    understanding = build_understanding(
        query="환불 조건 안내해줘",
        intent="REFUND_POLICY",
        slots={},
    )

    first = decide_route(
        understanding,
        has_user=False,
        has_pending_action=False,
        pending_state=None,
        is_reference_query=False,
        has_selection_state=False,
    )
    second = decide_route(
        understanding,
        has_user=False,
        has_pending_action=False,
        pending_state=None,
        is_reference_query=False,
        has_selection_state=False,
    )

    assert first.route == ROUTE_ANSWER
    assert second.route == first.route
    assert second.reason_code == first.reason_code
