# B-0368 — Chat Source Trust Scoring + Answer Reliability Label

## Priority
- P1

## Dependencies
- B-0353, B-0360, B-0365

## Goal
답변 근거의 신뢰도/최신성을 정량화해, 챗봇이 근거가 약한 답변을 자동으로 보수적으로 처리하도록 만든다.

## Non-goals
- 도메인 지식 원천 시스템 자체를 신규 구축하지 않는다.
- 사용자별 개인화 신뢰도 모델 학습은 범위 외다.

## Scope
### 1) Source trust registry
- 출처 타입별 신뢰등급(공식 정책/이벤트/공지/사용자생성) 정의
- source freshness와 trust score를 함께 관리

### 2) Retrieval + rerank integration
- trust score를 검색/재정렬 점수에 반영
- 저신뢰/만료 문서는 상위노출 제한

### 3) Answer reliability label
- 답변마다 reliability level(`HIGH/MEDIUM/LOW`) 산출
- LOW일 때는 확답 금지 + 확인 필요 문구/추가 경로 제공

### 4) Guardrail policy
- 낮은 신뢰도에서 민감 액션 인텐트 차단 또는 상담 전환
- trust score 산식 버전 관리

## Data / Schema
- `chat_source_trust_policy` (new): source_type, trust_weight, freshness_ttl, version
- `chat_answer_reliability_audit` (new): request_id, answer_id, reliability_level, trust_inputs, created_at
- 계약(`contracts/`) 변경이 필요하면 별도 PR로 분리

## Observability
- `chat_answer_reliability_total{level}`
- `chat_low_reliability_block_total{intent}`
- `chat_source_trust_distribution{source_type}`
- `chat_stale_source_used_total`
- `chat_reliability_level_shift_total{from,to}`

## Test / Validation
- 신뢰도 등급 산식 단위 테스트
- 동일 질의에서 trust boost 적용 전/후 비교 평가
- 저신뢰 답변 확답 금지 회귀 테스트
- 최신/만료 source 혼합 상황에서 reliability 산출 회귀 테스트

## DoD
- 근거 부족/오래된 정보 기반 오답률 감소
- LOW 신뢰도 응답의 안전 fallback 일관성 확보
- 신뢰도 레이블이 대시보드와 응답 payload에서 추적 가능
- source trust 정책 버전 변경 이력 감사 가능

## Codex Prompt
Add trust-aware chat grounding:
- Build source trust registry and freshness-aware scoring.
- Generate per-answer reliability labels and enforce low-confidence guardrails.
- Track trust metrics and validate regression on stale/weak evidence cases.
