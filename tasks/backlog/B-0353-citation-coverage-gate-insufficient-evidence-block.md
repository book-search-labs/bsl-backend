# B-0353 — 근거 강제 게이트 강화 (citation coverage + insufficient-evidence block)

## Priority
- P0 (환각 억제 핵심)

## Dependencies
- B-0351 (/chat 오류/응답 표준)

## Goal
근거 없는 생성 답변을 원천 차단하고, 근거 부족 시 명시적으로 답변 보류한다.

## Why
- 환각 감소의 핵심은 근거 커버리지 게이트
- citations가 있어도 답변 본문과 매핑되지 않으면 신뢰 불가

## Scope
### 1) Citation coverage 계산
- 문장/세그먼트 단위로 citation 연결률 계산
- `coverage = cited_segments / total_segments`
- 최소 임계치 미달 시 생성 답변 차단

### 2) Evidence sufficiency 판단
- retrieval score/다양성/중복 기준으로 충분성 점수 계산
- insufficient 상태 응답 포맷 표준화

### 3) Answer-citation 정합성 검증 (신규)
- 답변 문장과 인용 스니펫 간 entailment 검사(룰 기반 또는 NLI 기반)
- 불일치율이 높으면 "근거 부족"으로 강등

### 4) Prompt 강화
- "근거 없는 추론 금지" 시스템 지시 강화
- 인용 번호 없는 단정 문장 제한

### 5) 회귀 테스트
- 근거 없는 질문/애매 질문/오정보 유도 질문 세트 테스트

## Non-goals
- 멀티턴 메모리 품질 개선

## DoD
- 근거 부족 케이스에서 답변 대신 부족 안내 반환
- coverage/정합성 지표가 로그/메트릭으로 남음
- 환각 리포트 상위 케이스 재현셋 통과

## Interfaces
- `POST /v1/chat`
- (optional) `POST /internal/chat/verify-grounding`

## Observability
- `chat_citation_coverage_hist`
- `chat_grounding_mismatch_total`
- `chat_insufficient_evidence_total`

## Codex Prompt
Strengthen groundedness gate:
- Compute citation coverage and block low-coverage answers.
- Add answer-to-citation consistency checks.
- Return insufficient-evidence response when support is weak.
