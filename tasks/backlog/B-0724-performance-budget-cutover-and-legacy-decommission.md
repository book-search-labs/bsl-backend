# B-0724 — Performance Budget Cutover + Legacy Decommission

## Priority
- P2

## Dependencies
- B-0714
- B-0723

## Goal
전면 리라이트 엔진의 성능/비용/SLO를 검증한 뒤 안전하게 cutover하고 legacy 엔진을 단계적으로 폐기한다.

## Scope
### 1) Performance budget
- 경로별 p95/p99 목표 정의(non-LLM vs LLM)
- 토큰/호출량/툴 호출량 budget 상한 설정
- 성능 예산 위반 시 자동 경고/승격 차단

### 2) Cutover plan
- 트래픽 단계: 10% -> 25% -> 50% -> 100%
- 각 단계별 minimum dwell time 및 승격 조건
- 실패 시 자동/수동 rollback 경로 병행

### 3) Legacy decommission
- 2주 안정화 후 legacy read-path 비활성화
- legacy 전용 코드/플래그/대시보드 정리 계획
- decommission 체크리스트 문서화

### 4) Post-cutover verification
- SLO, 비용, 오실행, 권한 사고 지표 추적
- 운영 리뷰(주간)와 잔여 리스크 등록

## Test / Validation
- load/perf tests
- rollout + rollback drill tests
- post-cutover smoke and incident simulation tests

## DoD
- 100% 전환 후 SLO와 비용 예산을 유지한다.
- legacy 복구 경로를 제외한 주 실행 경로가 정리된다.
- 운영팀이 cutover/decommission 절차를 runbook대로 재현 가능하다.

## Codex Prompt
Complete rewrite rollout with performance/cost safeguards:
- Define cutover budgets and promotion gates.
- Run staged traffic migration with rollback drills.
- Decommission legacy engine safely after stabilization.
