from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app


def base_params() -> dict[str, str]:
    return {
        "sessionId": "localsim-101-ab12cd34",
        "paymentId": "101",
        "orderId": "9001",
        "amount": "12900",
        "currency": "KRW",
        "successUrl": "http://localhost:5174/payment/process/9001",
        "failUrl": "http://localhost:5174/payment/result/9001",
        "webhookUrl": "http://localhost:8091/api/v1/payments/webhook/local_sim",
        "provider": "LOCAL_SIM",
    }


def test_checkout_renders_required_identifiers_and_actions():
    client = TestClient(app)

    response = client.get("/checkout", params=base_params())

    assert response.status_code == 200
    assert "PG Simulator Checkout" in response.text
    assert "localsim-101-ab12cd34" in response.text
    assert "성공 (즉시)" in response.text
    assert "실패 (즉시)" in response.text
    assert "성공 (3초 지연)" in response.text
    assert "실패 (5초 지연)" in response.text


def test_success_redirect_includes_payment_key_and_payment_id():
    client = TestClient(app)

    response = client.get(
        "/simulate",
        params={**base_params(), "action": "success"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["paymentId"] == ["101"]
    assert query["payment_id"] == ["101"]
    assert query["paymentKey"][0].startswith("sim_pk_")
    assert query["payment_key"][0] == query["paymentKey"][0]


def test_fail_redirect_includes_code_and_message():
    client = TestClient(app)

    response = client.get(
        "/simulate",
        params={**base_params(), "action": "fail"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["paymentId"] == ["101"]
    assert query["code"] == ["PG_SIM_DECLINED"]
    assert query["message"] == ["결제가 취소되었거나 승인에 실패했습니다."]


def test_delayed_success_redirect_waits_before_redirect():
    client = TestClient(app)

    with patch("app.main.time.sleep") as mocked_sleep:
        response = client.get(
            "/simulate",
            params={**base_params(), "action": "success", "delay_sec": "3"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    mocked_sleep.assert_called_once_with(3)


def test_delayed_fail_redirect_waits_before_redirect():
    client = TestClient(app)

    with patch("app.main.time.sleep") as mocked_sleep:
        response = client.get(
            "/simulate",
            params={**base_params(), "action": "fail", "delay_sec": "5"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    mocked_sleep.assert_called_once_with(5)
