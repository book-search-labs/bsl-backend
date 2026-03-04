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

## Implementation Update (2026-03-03, Bundle 1)
- [x] Correction memory schema gate 추가
  - `scripts/eval/chat_correction_memory_schema.py`
  - 필수 필드/스코프 누락 및 승인상태 정합성 검증
  - active 교정의 만료/중복 trigger 패턴 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_correction_memory_schema.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CORRECTION_MEMORY_SCHEMA=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Correction approval workflow gate 추가
  - `scripts/eval/chat_correction_approval_workflow.py`
  - 작성/승인/활성화 전이 위반 및 reviewer/actor 누락 검증
  - approval/activation 지연 p95 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_correction_approval_workflow.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CORRECTION_APPROVAL_WORKFLOW=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Correction retrieval integration gate 추가
  - `scripts/eval/chat_correction_retrieval_integration.py`
  - correction precedence 위반(precedence violation) 검증
  - 정책 충돌 미처리(unhandled conflict) 및 reason_code 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_correction_retrieval_integration.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CORRECTION_RETRIEVAL_INTEGRATION=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Correction quality safeguards gate 추가
  - `scripts/eval/chat_correction_quality_safeguards.py`
  - correction 과적용(overapply) 및 precision gate fail 검증
  - false-positive open/rollback SLA breach/audit 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_correction_quality_safeguards.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_CORRECTION_QUALITY_SAFEGUARDS=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 5)
- [x] Baseline drift governance 추가 (4개 gate 공통)
  - `scripts/eval/chat_correction_memory_schema.py`
  - `scripts/eval/chat_correction_approval_workflow.py`
  - `scripts/eval/chat_correction_retrieval_integration.py`
  - `scripts/eval/chat_correction_quality_safeguards.py`
  - `--baseline-report` 입력 + `compare_with_baseline(...)` + `gate.baseline_failures` + `gate_pass` 출력
  - payload 공통 필드(`source`, `derived.summary`) 추가
- [x] 단위 테스트 확장 (baseline regression)
  - `scripts/eval/test_chat_correction_memory_schema.py`
  - `scripts/eval/test_chat_correction_approval_workflow.py`
  - `scripts/eval/test_chat_correction_retrieval_integration.py`
  - `scripts/eval/test_chat_correction_quality_safeguards.py`
- [x] CI baseline 옵션/드리프트 env 연동
  - `scripts/test.sh`
  - baseline fixture 경로 자동 연결 + `*_DROP`/`*_INCREASE` env 추가
- [x] baseline fixture 추가
  - `services/query-service/tests/fixtures/chat_correction_memory_schema_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_correction_approval_workflow_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_correction_retrieval_integration_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_correction_quality_safeguards_baseline_v1.json`
- [x] 운영 문서 갱신
  - `docs/RUNBOOK.md` (B-0381 Bundle 1~4 baseline 실행 예시 + drift env 명시)
