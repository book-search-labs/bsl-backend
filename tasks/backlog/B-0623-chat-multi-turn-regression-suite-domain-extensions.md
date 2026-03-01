# B-0623 — Chat Multi-turn Regression Suite Expansion (Book Domain)

## Priority
- P2

## Dependencies
- B-0608
- B-0621
- B-0622

## Goal
도서 도메인 고빈도 멀티턴 패턴("다른 출판사", "더 쉬운 버전", "2번째")을 대규모 회귀셋으로 확장한다.

## Why
- 초기 20개 시드만으로는 실제 사용자 변형 표현을 커버하기 어려움

## Scope
### 1) Scenario expansion
- 100+ 시나리오 확장 (검색/추천/정책/주문 연계)
- 동의어/구어체/오탈자/권차 축약형 포함

### 2) Oracle design
- turn별 expected route/state/selection/actionability 정의
- answer text exact match 대신 claim/transition 중심 검증

### 3) Continuous curation
- 운영 실패 사례 자동 샘플링 -> 회귀셋 반영

## DoD
- 100+ 회귀셋이 CI에서 주기 실행된다.
- 신규 실패 사례가 1주 내 회귀셋에 편입된다.

## Interfaces
- eval fixtures
- failure curation pipeline

## Observability
- `chat_regression_suite_size{domain}`
- `chat_regression_new_case_ingest_total`

## Test / Validation
- fixture schema tests
- flaky scenario detection tests

## Codex Prompt
Expand multi-turn regression coverage:
- Build 100+ domain scenarios with route/state assertions.
- Continuously ingest production failures into the suite.
- Track suite growth and stability metrics.
