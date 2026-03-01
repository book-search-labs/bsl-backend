# B-0381 — Chat Operator-approved Correction Memory

## Priority
- P2

## Dependencies
- B-0366, B-0371, A-0144

## Goal
운영자가 승인한 수정 답변/주의사항을 챗봇 메모리로 반영해 반복 오류를 빠르게 줄인다.

## Non-goals
- 승인 없는 자동 자기학습은 허용하지 않는다.
- 개인 사용자 프라이빗 데이터는 교정 메모리에 저장하지 않는다.

## Scope
### 1) Correction memory schema
- correction_id, domain, trigger_pattern, approved_answer, expiry, owner
- 적용 범위(locale/channel/intent) 명시

### 2) Approval workflow
- 운영자 작성 -> 검토자 승인 -> 활성화
- 만료/비활성화/롤백 지원

### 3) Retrieval integration
- 일반 지식 검색 전 correction memory 선적용 우선순위
- 충돌 시 최신 승인 버전 우선 + 정책 엔진 연계

### 4) Quality safeguards
- 교정 문구 과적용 방지(precision gate)
- incorrect correction 신고 경로 + 즉시 차단

## Observability
- `chat_correction_memory_hit_total{domain}`
- `chat_correction_memory_override_total`
- `chat_correction_memory_rollback_total`
- `chat_correction_memory_false_positive_total`

## Test / Validation
- trigger pattern 매칭 정확성 테스트
- 승인/만료/롤백 워크플로 회귀 테스트
- 교정 적용 전후 오류 재발률 비교

## DoD
- 반복 오류 재발률 감소
- 승인기반 교정만 적용됨을 감사로그로 보장
- 교정 충돌/과적용 탐지 가능

## Codex Prompt
Implement approved correction memory for chat:
- Store operator-approved fixes with scope, expiry, and ownership.
- Apply corrections in retrieval with policy-safe precedence.
- Support approval lifecycle, rollback, and misuse detection metrics.
