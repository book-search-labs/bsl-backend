import json
import os
import sys
import time
import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from urllib import request, error

BASE_URL = os.environ.get("BFF_BASE_URL", "http://localhost:8088")
USER_ID = os.environ.get("USER_ID", "1001")
SKU_ID = os.environ.get("SKU_ID")
SELLER_ID = os.environ.get("SELLER_ID", "1")
RUN_REFUND = os.environ.get("RUN_REFUND", "0") == "1"
MOCK_WEBHOOK_SECRET = os.environ.get("PAYMENTS_MOCK_WEBHOOK_SECRET", "dev_mock_webhook_secret")
LOCAL_SIM_WEBHOOK_SECRET = os.environ.get("PAYMENTS_LOCAL_SIM_WEBHOOK_SECRET", "dev_local_sim_webhook_secret")

if not SKU_ID:
    print("SKU_ID is required (export SKU_ID=123)")
    sys.exit(1)


def call_json(method, path, payload=None, headers=None):
    url = BASE_URL.rstrip("/") + path
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("x-user-id", USER_ID)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data) if data else {}
    except error.HTTPError as exc:
        data = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {data}")
    except Exception as exc:
        raise RuntimeError(f"Request failed: {exc}")


def _sign(secret: str, payload_raw: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _resolve_webhook_secret(provider: str) -> str:
    normalized = (provider or "MOCK").strip().upper()
    if normalized == "LOCAL_SIM":
        return LOCAL_SIM_WEBHOOK_SECRET
    return MOCK_WEBHOOK_SECRET


def _simulate_success_webhook(payment: dict):
    payment_id = payment.get("payment_id")
    provider = (payment.get("provider") or "MOCK").strip().upper()
    webhook_provider_path = provider.lower()
    provider_payment_id = payment.get("checkout_session_id") or payment.get("provider_payment_id") or f"{provider.lower()}-{payment_id}"
    event_id = f"e2e-webhook-{payment_id}-{uuid.uuid4().hex[:8]}"

    payload = {
        "event_id": event_id,
        "payment_id": payment_id,
        "status": "SUCCESS",
        "provider": provider,
        "provider_payment_id": provider_payment_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    payload_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    secret = _resolve_webhook_secret(provider)
    headers = {
        "X-Event-Id": event_id,
    }
    if secret:
        headers["X-Signature"] = _sign(secret, payload_raw)
    return call_json("POST", f"/api/v1/payments/webhook/{webhook_provider_path}", payload, headers=headers)


def _wait_for_payment_status(payment_id: int, expected_status: str, timeout_sec: int = 15):
    deadline = time.time() + max(timeout_sec, 1)
    while time.time() < deadline:
        current = call_json("GET", f"/api/v1/payments/{payment_id}")
        payment = current.get("payment", {})
        status = payment.get("status")
        if status == expected_status:
            return payment
        time.sleep(1)
    final_state = call_json("GET", f"/api/v1/payments/{payment_id}").get("payment", {})
    raise RuntimeError(
        f"Payment status did not reach {expected_status} within {timeout_sec}s. current={final_state.get('status')}"
    )


def main():
    print("[1] Search smoke...")
    try:
        call_json("POST", "/search", {"query": {"raw": "해리포터"}})
    except Exception as exc:
        print(f"Search warning: {exc}")

    print("[2] Load cart...")
    cart_resp = call_json("GET", "/api/v1/cart")
    cart = cart_resp.get("cart")

    print("[3] Add cart item...")
    cart_resp = call_json(
        "POST",
        "/api/v1/cart/items",
        {"skuId": int(SKU_ID), "sellerId": int(SELLER_ID), "qty": 1},
    )
    cart = cart_resp.get("cart")

    print("[4] Checkout + address...")
    checkout = call_json("GET", "/api/v1/checkout")
    addresses = checkout.get("addresses", [])
    if addresses:
        address_id = addresses[0].get("address_id")
    else:
        address = call_json(
            "POST",
            "/api/v1/addresses",
            {
                "name": "E2E User",
                "phone": "010-0000-0000",
                "zip": "00000",
                "addr1": "Seoul",
                "addr2": "E2E",
                "isDefault": True,
            },
        )
        address_id = address.get("address", {}).get("address_id")

    if not address_id:
        raise RuntimeError("Failed to create or load address")

    print("[5] Create order...")
    order_resp = call_json(
        "POST",
        "/api/v1/orders",
        {
            "cartId": cart.get("cart_id"),
            "shippingAddressId": address_id,
            "paymentMethod": "CARD",
            "idempotencyKey": f"e2e_{uuid.uuid4().hex}",
        },
    )
    order = order_resp.get("order")
    order_id = order.get("order_id")
    if not order_id:
        raise RuntimeError("Order creation failed")

    print("[6] Create payment...")
    payment_resp = call_json(
        "POST",
        "/api/v1/payments",
        {"orderId": order_id, "amount": order.get("total_amount"), "method": "CARD"},
    )
    payment = payment_resp.get("payment")
    payment_id = payment.get("payment_id")
    if not payment_id:
        raise RuntimeError("Payment creation failed")

    print("[7] Mock payment complete...")
    try:
        call_json("POST", f"/api/v1/payments/{payment_id}/mock/complete", {"result": "SUCCESS"})
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 404" in message:
            print("  - /mock/complete unavailable; fallback to webhook capture")
            _simulate_success_webhook(payment)
        else:
            raise

    _wait_for_payment_status(payment_id, "CAPTURED")

    print("[8] Create shipment...")
    shipment_resp = call_json("POST", "/api/v1/shipments", {"orderId": order_id})
    shipment = shipment_resp.get("shipment")
    shipment_id = shipment.get("shipment_id")
    if shipment_id:
        call_json(
            "POST",
            f"/api/v1/shipments/{shipment_id}/tracking",
            {"carrierCode": "CJ", "trackingNumber": f"E2E-{shipment_id}"},
        )
        call_json(
            "POST",
            f"/api/v1/shipments/{shipment_id}/mock/status",
            {"status": "DELIVERED"},
        )

    if RUN_REFUND:
        print("[9] Request refund...")
        call_json(
            "POST",
            "/api/v1/refunds",
            {"orderId": order_id, "reasonCode": "CHANGE_OF_MIND"},
        )

    print("E2E commerce flow completed.")


if __name__ == "__main__":
    main()
