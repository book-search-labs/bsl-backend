# B-0352 — Chat degrade 정책 명시화 (LLM 장애 시 search-only fallback)

## Goal
LLM/MIS 장애 상황에서도 챗봇이 완전 실패하지 않고 근거 기반 축약 응답으로 동작하도록 한다.

## Why
- 운영에서 가장 치명적인 경험은 "무응답" 또는 빈 응답
- degrade 정책이 있으면 SLA를 지키고 장애 영향을 축소 가능

## Scope
### 1) Degrade condition 정의
- LLM timeout, 5xx, rate-limit, policy block
- rerank timeout/실패 시 retrieval-only 모드

### 2) Fallback response
- 답변이 아닌 "근거 요약 + 확인 링크" 형태
- reason_code 명시 (`degraded_llm_timeout` 등)

### 3) 품질 가드
- 근거가 없으면 답변 생성 금지
- fallback에서도 citation은 유지

### 4) 옵저버빌리티
- degrade_rate, reason별 카운트, stage latency

## Non-goals
- 멀티 벤더 자동 페일오버

## DoD
- LLM 다운 상황에서 /chat 성공 응답(축약/근거 포함) 반환
- 사용자에게 장애 원인 범주가 명확히 표시됨
- 운영 대시보드에서 degrade율 확인 가능

## Interfaces
- `POST /v1/chat`
- `POST /chat` (BFF)

## Codex Prompt
Implement degrade policy for chat:
- Detect LLM/rerank failures and return grounded fallback response.
- Preserve citations and include reason_code in response metadata.
- Emit degrade metrics by reason.
