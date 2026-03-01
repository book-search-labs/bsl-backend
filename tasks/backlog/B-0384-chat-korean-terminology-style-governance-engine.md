# B-0384 — Chat Korean Terminology + Style Governance Engine

## Priority
- P2

## Dependencies
- B-0354, B-0381, A-0147

## Goal
챗 답변의 한국어 용어/문체를 도메인 정책에 맞게 일관화해 사용자 혼란을 줄이고 브랜드 톤을 안정화한다.

## Scope
### 1) Terminology dictionary
- 금칙어/권장어/도메인 표준 용어 사전 관리
- 동의어/외래어 표기 규칙 정의

### 2) Style policy
- 존댓말/간결성/문장 길이/숫자 표기 규칙
- 상황별 톤 가이드(안내/사과/제한모드)

### 3) Runtime enforcement
- 생성 답변 post-process로 용어/문체 정규화
- 과도한 수정 감지 시 원문 유지 fallback

### 4) Governance loop
- 운영자 승인 기반 사전 업데이트
- 스타일 위반 사례 수집/개선 루프

## Observability
- `chat_term_normalization_applied_total{rule}`
- `chat_style_violation_total{type}`
- `chat_style_fallback_total{reason}`
- `chat_terminology_dictionary_version`

## Test / Validation
- 용어 표준화 단위 테스트
- 톤/문체 회귀 테스트
- 사용자 이해도 지표(A/B) 검증

## DoD
- 용어 불일치/모호 표현 감소
- 한국어 문체 일관성 향상
- 운영 승인 기반 사전 변경 이력 확보

## Codex Prompt
Implement Korean terminology and style governance for chat:
- Enforce approved term dictionary and response style policies.
- Normalize generated outputs while preserving meaning.
- Operate dictionary updates through audited approvals and metrics.
