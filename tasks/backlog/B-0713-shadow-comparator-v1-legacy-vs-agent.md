# B-0713 — Shadow Comparator v1 (Legacy vs Agent)

## Priority
- P1

## Dependencies
- B-0712
- B-0703

## Goal
shadow 트래픽에서 legacy 응답과 LangGraph 응답의 차이를 자동 수집/분류해 canary 진입 리스크를 낮춘다.

## Scope
### 1) Diff model
- 비교 필드: `status`, `reason_code`, `next_action`, `recoverable`, `citations_count`
- semantic diff: answer 텍스트 exact match 대신 핵심 필드 우선 비교

### 2) Classification
- diff 유형 분류: `ROUTE_DIFF`, `REASON_DIFF`, `ACTION_DIFF`, `CITATION_DIFF`
- 심각도 라벨: `INFO/WARN/BLOCKER`

### 3) Aggregation/reporting
- 세션/인텐트/토픽 단위 diff 비율 집계
- 상위 mismatch 케이스 샘플 자동 추출

### 4) Gate feed
- canary gate에서 참고 가능한 diff summary payload 생성
- blocker diff 비율 임계치 초과 시 승격 차단

## Test / Validation
- shadow comparator unit tests
- synthetic mismatch classification tests
- summary report generation tests

## DoD
- shadow 실행 결과가 자동으로 diff 리포트에 반영된다.
- 주요 mismatch 원인이 taxonomy로 분류된다.
- canary 승격 판단에 사용할 수 있는 지표가 제공된다.

## Codex Prompt
Implement shadow response comparator for rewrite rollout:
- Compare legacy and graph outputs by critical fields.
- Classify diffs into actionable categories.
- Emit gate-ready summary metrics and sampled cases.
