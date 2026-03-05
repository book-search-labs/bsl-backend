---
title: "26. LLM Gateway 심화: Citation 파서, SSE 프로토콜, 예산 차단"
slug: "bsl-backend-series-26-llm-gateway-citation-sse-budget"
series: "BSL Backend Technical Series"
episode: 26
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 26. LLM Gateway 심화: Citation 파서, SSE 프로토콜, 예산 차단

## 핵심 목표
LLM Gateway가 단순 프록시가 아니라, 출력 형식/비용/스트리밍 계약을 강제하는 계층임을 코드로 설명합니다.

핵심 구현 파일:
- `services/llm-gateway-service/app/api/routes.py`
- `services/llm-gateway-service/app/core/budget.py`
- `services/llm-gateway-service/app/core/limiter.py`
- `services/llm-gateway-service/app/core/audit.py`

## 1) `/v1/generate` 처리 순서
1. API key 검증 (`x-api-key`)
2. key별 RPM 제한 (`RateLimiter`)
3. provider 분기(`openai_compat` 또는 toy)
4. 비용 계산 후 budget 검사
5. 응답/감사 로그 기록

실패 시 `HTTPException`으로 즉시 종료합니다.

## 2) citation 필수 모드 파서
`_parse_answer()`는 `citations_required=true`일 때 아래를 강제합니다.

1. JSON payload 추출 시도
2. `answer` + `citations` 정규화
3. citations 비어 있으면 본문 bracket citation 재추출
4. allowed citation set으로 최종 필터링

실패 reason:
- `invalid_json`
- `missing_citations`

## 3) allowed citation 필터
`_allowed_citations()`는 request context chunk의 `citation_key` 집합을 만듭니다.

모델이 임의 citation 키를 생성해도, allowed 집합에 없는 값은 전부 제거됩니다.

## 4) OpenAI 메시지 구성 규칙
`_build_openai_messages()`는 citations_required일 때 시스템 프롬프트로 JSON 계약을 강제합니다.

추가로 context chunk를 `Sources:` 블록으로 넣어 citation grounding 범위를 명시합니다.

## 5) SSE 이벤트 계약
스트리밍 응답은 다음 이벤트만 사용합니다.

- `meta`
- `delta`
- `error`
- `done`

`_openai_stream()`은 예외가 나도 `error` 후 `done`을 보내도록 구현되어, 클라이언트 상태머신이 멈추지 않습니다.

## 6) budget 검사 타이밍
스트림 모드에서는 두 번 budget을 확인합니다.

1. 시작 전 reserved 토큰 비용 검사
2. 최종 answer 토큰 비용 검사 후 차감

즉, 시작 가능성과 완료 가능성을 분리해 제어합니다.

## 7) BudgetManager 모드
`BudgetManager`는 두 모드를 지원합니다.

- 메모리 모드: `_spent_usd` 누적
- Redis 모드: Lua script(`INCRBYFLOAT + TTL`) 원자 처리

Redis 모드에서는 budget window TTL을 key에 자동 적용합니다.

## 8) RateLimiter 구현
`RateLimiter.allow()`는 key별 deque sliding window(60초)로 구현됩니다.

- 오래된 이벤트 제거
- 현재 이벤트 수 >= rpm이면 차단
- 아니면 append 후 통과

로컬 단일 인스턴스에 맞춘 경량 구현입니다.

## 9) 감사 로그 이중 sink
`_audit_event()`는 파일/DB sink를 각각 `try`로 감쌉니다.

- 파일 실패가 DB 기록을 막지 않음
- DB 실패가 API 응답을 막지 않음

기록 필드:
- trace/request id
- provider/model
- tokens/cost
- status/reason_code

## 10) 토큰/비용 계산
기본 추정:
- token ~= `len(text)/4`
- cost = `tokens/1000 * cost_per_1k_tokens`

실제 OpenAI usage가 있으면 total_tokens를 우선 사용합니다.

## 11) 실패 코드 일관성
대표 실패 응답:
- unauthorized -> `401`
- rate_limited -> `429`
- budget_exceeded -> `429`
- provider timeout -> `504`
- provider error -> `502`

Chat 오케스트레이터에서 이유 코드 매핑이 쉬워집니다.

## 12) 로컬 검증
```bash
curl -N -sS 'http://localhost:8010/v1/generate?stream=true' \
  -H 'x-api-key: local-dev-key' \
  -H 'Content-Type: application/json' \
  -d '{"model":"toy","stream":true,"citations_required":true,"messages":[{"role":"user","content":"요약해 주세요"}],"context":{"chunks":[{"citation_key":"doc:1","content":"..."}]}}'
```

확인 포인트:
1. 이벤트 순서(`meta -> delta* -> done`)
2. citation 누락 시 `status=fallback`
3. budget 초과 시 `error + done`

## 13) 구현상 의도
LLM 계층의 핵심은 "좋은 문장 생성"이 아니라, "계약 위반을 허용하지 않는 것"입니다.

이 게이트웨이는 모델 품질과 무관하게, 응답 형식·비용·감사를 강제하는 안전 레이어로 설계되어 있습니다.
