# B-0627 — Chat Recommendation Experiment Loop + Quality Gate

## Priority
- P2

## Dependencies
- B-0622
- B-0623

## Goal
추천 품질 개선을 위한 실험/평가 루프를 운영 표준으로 정착시킨다.

## Why
- 추천 품질은 카탈로그 변화와 사용자 취향 변화에 따라 지속 튜닝이 필요

## Scope
### 1) Experiment framework
- 후보 생성 전략 A/B (유사도/카테고리/인기도 가중)
- explain 템플릿 A/B

### 2) Quality gate
- 존재성/재고성/다양성/클릭률 지표 기준선
- 회귀 시 rollout 차단

### 3) Feedback loop
- dislike 이유 수집 -> feature/prompt 개선 backlog 자동 생성

## DoD
- 추천 실험 결과가 주기 리포트로 생성된다.
- 품질 기준 미달 실험은 자동 중단된다.
- feedback 기반 개선 항목이 백로그로 연동된다.

## Interfaces
- experiment config API
- eval/report pipeline

## Observability
- `chat_recommend_experiment_total{variant,status}`
- `chat_recommend_quality_gate_block_total{reason}`

## Test / Validation
- experiment assignment tests
- quality gate threshold tests
- feedback ingestion tests

## Codex Prompt
Build recommendation experimentation and quality controls:
- Run A/B tests on candidate generation and explanation strategies.
- Gate rollouts on recommendation quality thresholds.
- Convert user feedback into actionable improvement tasks.
