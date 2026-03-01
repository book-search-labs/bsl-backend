import hmac
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="pg-simulator")

DEFAULT_SECRET = os.getenv("PG_SIM_WEBHOOK_SECRET", "dev_local_sim_webhook_secret")
DEFAULT_PROVIDER = os.getenv("PG_SIM_PROVIDER", "LOCAL_SIM")
DEFAULT_TIMEOUT = float(os.getenv("PG_SIM_WEBHOOK_TIMEOUT_SEC", "3.0"))


def _append_query(url: str, extra: dict[str, Any]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in extra.items():
        if value is None:
            continue
        query[key] = str(value)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def _sign(payload_raw: str) -> str:
    signature = hmac.new(DEFAULT_SECRET.encode("utf-8"), payload_raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={signature}"


def _build_checkout_link(base_query: dict[str, str], action: str, delay_sec: int = 0, duplicate_count: int = 1, no_return: int = 0) -> str:
    query = dict(base_query)
    query["action"] = action
    query["delay_sec"] = str(delay_sec)
    query["duplicate_count"] = str(duplicate_count)
    query["no_return"] = str(no_return)
    return "/simulate?" + urlencode(query)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "pg-simulator"}


@app.get("/checkout", response_class=HTMLResponse)
def checkout(
    session_id: str = Query(...),
    payment_id: int = Query(...),
    order_id: int = Query(...),
    amount: int = Query(...),
    currency: str = Query("KRW"),
    return_url: str = Query(...),
    webhook_url: str = Query(...),
    provider: str = Query(DEFAULT_PROVIDER),
) -> HTMLResponse:
    base_query = {
        "session_id": session_id,
        "payment_id": str(payment_id),
        "order_id": str(order_id),
        "amount": str(amount),
        "currency": currency,
        "return_url": return_url,
        "webhook_url": webhook_url,
        "provider": provider,
    }

    rows = [
        ("성공 (즉시)", _build_checkout_link(base_query, "success")),
        ("실패 (즉시)", _build_checkout_link(base_query, "fail")),
        ("성공 (5초 지연)", _build_checkout_link(base_query, "success", delay_sec=5)),
        ("성공 (10초 지연)", _build_checkout_link(base_query, "success", delay_sec=10)),
        ("성공 + 중복 웹훅 3회", _build_checkout_link(base_query, "success", duplicate_count=3)),
        ("웹훅만 전송 (복귀 없음)", _build_checkout_link(base_query, "success", no_return=1)),
    ]

    buttons = "\n".join(
        f'<a class="btn" href="{escape(link)}">{escape(label)}</a>' for label, link in rows
    )

    html = f"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PG Simulator</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; margin: 0; }}
    .wrap {{ max-width: 760px; margin: 32px auto; background: #fff; border: 1px solid #ddd; border-radius: 12px; padding: 24px; }}
    h1 {{ margin-top: 0; }}
    .meta {{ color: #444; margin-bottom: 16px; }}
    .meta dt {{ font-weight: 700; }}
    .meta dd {{ margin: 0 0 8px 0; word-break: break-all; }}
    .actions {{ display: grid; gap: 10px; margin-top: 20px; }}
    .btn {{ display: inline-block; padding: 12px 14px; background: #111; color: #fff; border-radius: 8px; text-decoration: none; }}
    .btn:hover {{ opacity: .9; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>PG Simulator Checkout</h1>
    <dl class="meta">
      <dt>session_id</dt><dd>{escape(session_id)}</dd>
      <dt>payment_id</dt><dd>{payment_id}</dd>
      <dt>order_id</dt><dd>{order_id}</dd>
      <dt>amount</dt><dd>{amount} {escape(currency)}</dd>
      <dt>provider</dt><dd>{escape(provider)}</dd>
      <dt>return_url</dt><dd>{escape(return_url)}</dd>
      <dt>webhook_url</dt><dd>{escape(webhook_url)}</dd>
    </dl>
    <div class="actions">
      {buttons}
    </div>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=html)


@app.get("/simulate")
def simulate(
    session_id: str = Query(...),
    payment_id: int = Query(...),
    order_id: int = Query(...),
    amount: int = Query(...),
    currency: str = Query("KRW"),
    return_url: str = Query(...),
    webhook_url: str = Query(...),
    provider: str = Query(DEFAULT_PROVIDER),
    action: str = Query("success"),
    delay_sec: int = Query(0),
    duplicate_count: int = Query(1),
    no_return: int = Query(0),
) -> HTMLResponse | RedirectResponse:
    normalized = action.strip().lower()
    status = "CAPTURED" if normalized == "success" else "FAILED"
    event_id = f"pgsim-{payment_id}-{uuid.uuid4().hex[:12]}"

    payload = {
        "event_id": event_id,
        "payment_id": payment_id,
        "session_id": session_id,
        "status": status,
        "amount": amount,
        "currency": currency,
        "provider": provider,
        "provider_payment_id": session_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }

    if delay_sec > 0:
        time.sleep(delay_sec)

    payload_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    headers = {
        "Content-Type": "application/json",
        "X-Event-Id": event_id,
        "X-Signature": _sign(payload_raw),
    }

    results: list[tuple[int, str]] = []
    count = min(max(duplicate_count, 1), 3)
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        for _ in range(count):
            try:
                resp = client.post(webhook_url, content=payload_raw.encode("utf-8"), headers=headers)
                results.append((resp.status_code, (resp.text or "")[:200]))
            except Exception as exc:
                results.append((599, str(exc)))

    if no_return == 1:
        body = "<br/>".join(f"[{code}] {escape(text)}" for code, text in results)
        return HTMLResponse(
            f"<h1>Webhook Sent Only</h1><p>event_id={escape(event_id)}</p><p>{body}</p>",
            status_code=200,
        )

    redirect_to = _append_query(
        return_url,
        {
            "payment_id": payment_id,
            "session_id": session_id,
            "pg_status": status,
            "event_id": event_id,
            "webhook_http": results[0][0] if results else None,
        },
    )
    return RedirectResponse(url=redirect_to, status_code=302)
