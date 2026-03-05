import hmac
import hashlib
import json
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

import httpx
from fastapi import FastAPI, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="pg-simulator")

DEFAULT_SECRET = os.getenv("PG_SIM_WEBHOOK_SECRET", "dev_local_sim_webhook_secret")
DEFAULT_PROVIDER = os.getenv("PG_SIM_PROVIDER", "LOCAL_SIM")
DEFAULT_TIMEOUT = float(os.getenv("PG_SIM_WEBHOOK_TIMEOUT_SEC", "3.0"))
LOCALHOST_FALLBACK_HOST = os.getenv("PG_SIM_LOCALHOST_FALLBACK_HOST", "host.docker.internal")


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


def _replace_url_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    netloc = host
    if ":" in parsed.netloc:
        _, port = parsed.netloc.rsplit(":", 1)
        if port.isdigit():
            netloc = f"{host}:{port}"
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _is_localhost_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _can_resolve_host(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
        return True
    except OSError:
        return False


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

    scenarios = [
        (
            "결제 승인",
            "즉시 성공 웹훅 1회 전송 후 주문 화면으로 복귀",
            _build_checkout_link(base_query, "success"),
            "success",
            True,
        ),
        (
            "결제 취소",
            "결제를 취소하고 이전 화면으로 복귀",
            _build_checkout_link(base_query, "cancel"),
            "cancel",
            True,
        ),
        (
            "결제 실패",
            "즉시 실패 웹훅 1회 전송 후 주문 화면으로 복귀",
            _build_checkout_link(base_query, "fail"),
            "danger",
            True,
        ),
        (
            "승인 (5초 지연)",
            "성공 웹훅을 5초 뒤 전송해 지연 처리 경로를 검증",
            _build_checkout_link(base_query, "success", delay_sec=5),
            "latency",
            False,
        ),
        (
            "승인 (10초 지연)",
            "성공 웹훅을 10초 뒤 전송해 폴링/타임아웃 경로를 검증",
            _build_checkout_link(base_query, "success", delay_sec=10),
            "latency",
            False,
        ),
        (
            "승인 + 중복 웹훅 3회",
            "동일 이벤트 중복 수신 시 멱등 처리 여부를 검증",
            _build_checkout_link(base_query, "success", duplicate_count=3),
            "duplicate",
            False,
        ),
        (
            "웹훅만 전송 (복귀 없음)",
            "브라우저 복귀 없이 백엔드 웹훅 처리만 검증",
            _build_checkout_link(base_query, "success", no_return=1),
            "webhook",
            False,
        ),
    ]

    quick_actions = "\n".join(
        f"""
        <a class="scenario-card tone-{tone}" href="{escape(link)}">
          <span class="scenario-title">{escape(label)}</span>
          <span class="scenario-desc">{escape(description)}</span>
        </a>
        """
        for label, description, link, tone, is_primary in scenarios
        if is_primary
    )
    advanced_actions = "\n".join(
        f"""
        <a class="scenario-card scenario-card-small tone-{tone}" href="{escape(link)}">
          <span class="scenario-title">{escape(label)}</span>
          <span class="scenario-desc">{escape(description)}</span>
        </a>
        """
        for label, description, link, tone, is_primary in scenarios
        if not is_primary
    )

    method_chips = "\n".join(
        [
            '<div class="method-chip is-selected">신용/체크카드</div>',
            '<div class="method-chip">현대카드</div>',
            '<div class="method-chip">계좌이체</div>',
            '<div class="method-chip">무통장입금</div>',
            '<div class="method-chip">토스페이</div>',
            '<div class="method-chip">네이버페이</div>',
            '<div class="method-chip">카카오페이</div>',
        ]
    )
    formatted_amount = f"{amount:,}"

    html = f"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>결제창 - LOCAL_SIM</title>
  <style>
    :root {{
      --bg: #e8edf3;
      --panel: #ffffff;
      --ink: #121926;
      --muted: #5b6678;
      --line: #dbe3ee;
      --accent: #0f172a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: 'Pretendard Variable', 'Pretendard', 'SUIT', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 620px at 10% -10%, #f6f9ff 0%, rgba(246, 249, 255, 0) 55%),
        linear-gradient(180deg, #ecf1f7 0%, var(--bg) 100%);
      padding: 24px;
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid rgba(22, 31, 48, 0.11);
      border-radius: 28px;
      box-shadow: 0 24px 50px rgba(19, 32, 56, 0.13);
      backdrop-filter: blur(8px);
      overflow: hidden;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(250, 252, 255, 0.82);
    }}
    .dots {{
      display: flex;
      gap: 8px;
      align-items: center;
    }}
    .dot {{
      width: 11px;
      height: 11px;
      border-radius: 50%;
    }}
    .dot-red {{ background: #f87171; }}
    .dot-yellow {{ background: #fbbf24; }}
    .dot-green {{ background: #34d399; }}
    .sim-badge {{
      border-radius: 999px;
      padding: 4px 10px;
      background: #e7eef8;
      color: #334155;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.08em;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
    }}
    .order-title {{
      margin: 0;
      font-size: 1.72rem;
      font-weight: 900;
      letter-spacing: -0.02em;
    }}
    .order-caption {{
      margin: 6px 0 16px;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .amount-box {{
      border-radius: 14px;
      border: 1px solid #cfd8e5;
      background: linear-gradient(180deg, #f9fbff 0%, #f2f6fb 100%);
      padding: 14px;
      margin-bottom: 14px;
    }}
    .amount-label {{
      font-size: 0.74rem;
      color: #6b7280;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    .amount-value {{
      margin-top: 4px;
      font-size: 1.58rem;
      font-weight: 900;
      letter-spacing: -0.01em;
    }}
    .order-ids {{
      margin-top: 2px;
      color: #6b7280;
      font-size: 0.84rem;
    }}
    .meta-grid {{
      margin: 0;
      padding: 0;
      display: grid;
      gap: 10px;
    }}
    .meta-item {{
      border-radius: 12px;
      border: 1px solid #dde4ef;
      background: #f8fafd;
      padding: 10px 11px;
    }}
    .meta-key {{
      display: block;
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      color: #64748b;
      font-weight: 800;
      margin-bottom: 4px;
    }}
    .meta-value {{
      font-size: 0.87rem;
      color: #1e293b;
      word-break: break-all;
      line-height: 1.35;
      font-weight: 600;
    }}
    .pay-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .pay-title {{
      margin: 0;
      font-size: 1.45rem;
      font-weight: 900;
      letter-spacing: -0.01em;
    }}
    .pay-note {{
      margin: 0;
      color: var(--muted);
      font-size: 0.85rem;
    }}
    .method-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 9px;
      margin: 14px 0 16px;
    }}
    .method-chip {{
      min-height: 48px;
      border-radius: 12px;
      border: 1px solid #d7dee9;
      background: #f6f8fc;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      color: #384559;
      font-size: 0.84rem;
      font-weight: 700;
      padding: 6px 8px;
    }}
    .method-chip.is-selected {{
      border-color: #111827;
      background: #ffffff;
      box-shadow: 0 9px 16px rgba(15, 23, 42, 0.12);
    }}
    .scenario-row {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 11px;
      margin-top: 12px;
    }}
    .scenario-card {{
      display: block;
      border-radius: 14px;
      border: 1px solid #d9e1ec;
      text-decoration: none;
      background: #f8fafd;
      color: #1f2937;
      padding: 13px 14px;
      transition: all 0.16s ease;
    }}
    .scenario-card:hover {{
      transform: translateY(-1px);
      box-shadow: 0 10px 18px rgba(14, 21, 36, 0.11);
    }}
    .scenario-title {{
      display: block;
      font-size: 1rem;
      font-weight: 900;
      letter-spacing: -0.01em;
    }}
    .scenario-desc {{
      margin-top: 6px;
      display: block;
      color: #5f6c80;
      font-size: 0.81rem;
      line-height: 1.35;
    }}
    .scenario-card.tone-success {{
      background: linear-gradient(180deg, #f4fbf7 0%, #ecf8f1 100%);
      border-color: #b4e3c8;
    }}
    .scenario-card.tone-danger {{
      background: linear-gradient(180deg, #fff6f6 0%, #feeeee 100%);
      border-color: #f3b9b9;
    }}
    .scenario-card.tone-cancel {{
      background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
      border-color: #cbd5e1;
    }}
    .scenario-card.tone-latency {{
      background: linear-gradient(180deg, #fffaf0 0%, #fff5df 100%);
      border-color: #f2d6a7;
    }}
    .scenario-card.tone-duplicate {{
      background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
      border-color: #bfd2fa;
    }}
    .scenario-card.tone-webhook {{
      background: linear-gradient(180deg, #f8fafc 0%, #f2f6fb 100%);
      border-color: #cbd5e1;
    }}
    details.advanced {{
      margin-top: 12px;
      border-radius: 14px;
      border: 1px solid #d8e0ea;
      background: #f8fafd;
      padding: 11px;
    }}
    details.advanced summary {{
      cursor: pointer;
      list-style: none;
      font-size: 0.9rem;
      font-weight: 800;
      color: #334155;
    }}
    details.advanced summary::-webkit-details-marker {{
      display: none;
    }}
    .advanced-grid {{
      margin-top: 10px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 9px;
    }}
    .scenario-card-small .scenario-title {{
      font-size: 0.9rem;
    }}
    .scenario-card-small .scenario-desc {{
      font-size: 0.77rem;
    }}
    .foot-note {{
      margin-top: 13px;
      color: #6b7280;
      font-size: 0.8rem;
      line-height: 1.45;
      border-top: 1px solid #e3e8ef;
      padding-top: 11px;
    }}
    @media (max-width: 980px) {{
      body {{ padding: 14px; }}
      .layout {{ grid-template-columns: 1fr; padding: 14px; }}
      .method-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .scenario-row, .advanced-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <div class="toolbar">
      <div class="dots">
        <span class="dot dot-red"></span>
        <span class="dot dot-yellow"></span>
        <span class="dot dot-green"></span>
      </div>
      <span class="sim-badge">LOCAL_SIM</span>
    </div>
    <div class="layout">
      <aside class="panel">
        <h1 class="order-title">주문서</h1>
        <p class="order-caption">테스트 결제 세션 정보</p>
        <div class="amount-box">
          <div class="amount-label">총 결제 금액</div>
          <div class="amount-value">{formatted_amount} {escape(currency)}</div>
          <div class="order-ids">order #{order_id} · payment #{payment_id}</div>
        </div>
        <dl class="meta-grid">
          <div class="meta-item">
            <dt class="meta-key">SESSION ID</dt>
            <dd class="meta-value">{escape(session_id)}</dd>
          </div>
          <div class="meta-item">
            <dt class="meta-key">PROVIDER</dt>
            <dd class="meta-value">{escape(provider)}</dd>
          </div>
          <div class="meta-item">
            <dt class="meta-key">RETURN URL</dt>
            <dd class="meta-value">{escape(return_url)}</dd>
          </div>
          <div class="meta-item">
            <dt class="meta-key">WEBHOOK URL</dt>
            <dd class="meta-value">{escape(webhook_url)}</dd>
          </div>
        </dl>
      </aside>

      <section class="panel">
        <div class="pay-head">
          <h2 class="pay-title">결제 방법</h2>
          <span class="sim-badge">SANDBOX</span>
        </div>
        <p class="pay-note">실제 결제창 스타일의 UI이며, 아래 버튼으로 시나리오를 선택합니다.</p>
        <div class="method-grid">
          {method_chips}
        </div>
        <div class="scenario-row">
          {quick_actions}
        </div>
        <details class="advanced">
          <summary>고급 시나리오 보기</summary>
          <div class="advanced-grid">
            {advanced_actions}
          </div>
        </details>
        <div class="foot-note">
          기본 테스트는 <b>결제 승인</b> 또는 <b>결제 실패</b>만 선택하면 됩니다.<br/>
          지연/중복/복귀없음 시나리오는 장애 대응 및 멱등성 검증용입니다.
        </div>
      </section>
    </div>
  </main>
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
) -> Response:
    normalized = action.strip().lower()
    if normalized == "success":
        status = "CAPTURED"
    elif normalized == "cancel":
        status = "CANCELED"
    else:
        status = "FAILED"
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
    if status == "CANCELED":
        payload["reason"] = "user_canceled"

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
    fallback_url = None
    if _is_localhost_url(webhook_url) and LOCALHOST_FALLBACK_HOST and _can_resolve_host(LOCALHOST_FALLBACK_HOST):
        fallback_url = _replace_url_host(webhook_url, LOCALHOST_FALLBACK_HOST)

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        for _ in range(count):
            try:
                resp = client.post(webhook_url, content=payload_raw.encode("utf-8"), headers=headers)
                results.append((resp.status_code, (resp.text or "")[:200]))
            except Exception as exc:
                if fallback_url and fallback_url != webhook_url:
                    try:
                        resp = client.post(fallback_url, content=payload_raw.encode("utf-8"), headers=headers)
                        results.append((resp.status_code, f"fallback({fallback_url}) {(resp.text or '')[:160]}"))
                        continue
                    except Exception as fallback_exc:
                        results.append((599, f"{exc} | fallback_failed: {fallback_exc}"))
                        continue
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
