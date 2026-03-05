---
title: "10. LLM Gateway: 라우팅, 비용, 인용 강제"
slug: "bsl-backend-series-10-llm-gateway-routing"
series: "BSL Backend Technical Series"
episode: 10
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 10. LLM Gateway: 라우팅, 비용, 인용 강제

## 핵심 목표
LLM 호출을 Query Service에서 직접 하지 않고 게이트웨이로 분리해 인증, 비용, 출력 규격을 한 곳에서 통제합니다.

핵심 구현:
- `services/llm-gateway-service/app/api/routes.py`
- `core/settings.py`
- `core/limiter.py`
- `core/budget.py`
- `core/audit.py`, `core/audit_db.py`

## 1) 요청 처리 순서 (`POST /v1/generate`)
1. API key 확인 (`x-api-key`, `LLM_GATEWAY_KEYS`)
2. RPM 제한 (`RateLimiter`)
3. provider 분기 (`toy` / `openai_compat`)
4. 토큰 비용 계산 후 budget 검사
5. 응답 직렬화 + audit 기록

## 2) provider 라우팅
- `LLM_PROVIDER=toy`: 로컬 합성 응답
- `LLM_PROVIDER=openai_compat`: `/chat/completions` 호출

관련 env:
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`/`LLM_DEFAULT_MODEL`
- `LLM_TIMEOUT_MS`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`

## 3) 비용/예산 제어
`BudgetManager`는 메모리 또는 Redis를 사용합니다.

- `LLM_COST_BUDGET_USD`
- `LLM_COST_PER_1K`
- `LLM_BUDGET_WINDOW_SEC`
- `LLM_BUDGET_KEY`
- `LLM_REDIS_URL` (설정 시 Redis 모드)

budget 초과 시 다운스트림 호출 전에 차단합니다.

## 4) 인용 강제 로직(중요)
게이트웨이는 모델 출력에서 `answer`/`citations`를 파싱하고, 컨텍스트에 있는 citation key만 허용합니다.

대표 오류 태그:
- `invalid_json`
- `missing_citations`

즉, LLM이 포맷을 어겨도 게이트웨이에서 안전하게 보정/차단합니다.

## 5) 감사 로그
감사 로그 sink를 파일/DB로 분리했습니다.

- 파일: `LLM_AUDIT_LOG_PATH`
- DB: `LLM_AUDIT_DB_ENABLED` + `LLM_AUDIT_DB_*`

side project에서도 “어떤 요청이 얼마 비용으로 실패/성공했는지”를 추적하기 충분했습니다.

## 6) 스트리밍 이벤트
SSE 모드에서 이벤트를 명시적으로 보냅니다.

- `meta`
- `delta`
- `error`
- `done`

클라이언트는 이 이벤트를 그대로 UI 상태머신에 연결할 수 있습니다.

## 로컬 점검
```bash
curl -sS http://localhost:8010/v1/generate \
  -H 'x-api-key: local-dev-key' \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"...","context":{"chunks":[]}}' | jq
```

## 7) generate 엔드포인트 내부 분기
`routes.py` 기준으로 `POST /v1/generate`는 아래처럼 분기합니다.

1. API key 검사
2. RateLimiter 검사
3. provider가 `openai_compat`이면 외부 호출 경로
4. 아니면 `toy` 합성 응답 경로
5. stream 옵션이면 SSE 응답

동일 endpoint에서 provider별 동작을 숨겨 호출자 단순성을 유지합니다.

## 8) RateLimiter 구현 특성
`limiter.py`는 key별 deque를 사용해 60초 sliding window를 구현합니다.

1. 오래된 이벤트 제거
2. 현재 window 이벤트 수 비교
3. rpm 초과 시 차단

복잡한 분산 제한이 아니라 로컬 개발에 적합한 단순 메모리 limiter입니다.

## 9) BudgetManager Redis 모드
`budget.py`는 Redis 설정 시 Lua script로 `INCRBYFLOAT + TTL`을 원자적으로 처리합니다.

핵심:
1. 예산 누적 key 자동 생성
2. TTL이 없으면 window TTL 설정
3. spend 전 `can_spend` 확인

로컬 단일 인스턴스에서는 메모리 모드만으로도 충분합니다.

## 10) 인용 파싱 파이프라인
`_parse_answer()`는 다음 순서로 citations를 계산합니다.

1. citations_required=false면 무시
2. allowed citation key 집합 구성
3. JSON payload 추출 시도
4. `citations` 필드 정규화
5. 없으면 본문 bracket citation 재추출

결과적으로 `invalid_json`과 `missing_citations`를 reason으로 남깁니다.

## 11) 스트리밍(SSE) 에러 처리
`_openai_stream()`은 실패 상황에서도 이벤트 계약을 유지합니다.

1. 실패 시 `error` 이벤트 송신
2. 항상 `done` 이벤트 송신
3. audit 로그는 실패 상태로 기록

클라이언트가 중간 상태에서 멈추지 않도록 protocol을 강제한 구조입니다.

## 12) 감사 로그 설계 포인트
파일 감사(`append_audit`)와 DB 감사(`append_audit_db`)를 분리해 sink 실패가 전체 요청 실패로 번지지 않게 했습니다.

필수 기록 필드:
- trace_id, request_id, provider, model
- tokens, cost_usd
- status, reason_code
