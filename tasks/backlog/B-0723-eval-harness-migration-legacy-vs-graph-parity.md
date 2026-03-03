# B-0723 — Eval Harness Migration (Legacy vs Graph Parity)

## Priority
- P2

## Dependencies
- B-0713
- B-0715
- B-0721

## Goal
기존 평가 체계를 LangGraph 기준으로 확장해 legacy 대비 parity와 회귀 차단을 자동화한다.

## Scope
### 1) Unified eval matrix
- recommend/rollout/semantic/reason_code/regression/summary 게이트를 graph metadata와 연동
- 리포트에 `engine`, `graph_run_id`, `node_path` 필드 추가

### 2) Parity checks
- legacy vs graph 응답 parity 측정
- parity 실패 케이스 자동 샘플링 및 분류

### 3) Baseline governance
- eval baseline 갱신 정책 수립(승인자/주기/근거)
- baseline drift 감지 시 경고/차단 규칙

### 4) CI pipeline update
- `RUN_CHAT_ALL_EVALS=1`에서 graph 관련 게이트 포함
- 실패 시 원인 링크(리포트 경로) 표준 출력

## Test / Validation
- eval script unit tests
- end-to-end eval pipeline smoke tests
- baseline regression tests

## DoD
- graph 엔진 관련 품질 게이트가 CI에서 자동 실행된다.
- parity 실패 시 원인 분류와 샘플이 제공된다.
- baseline 관리 절차가 문서화되어 재현 가능하다.

## Codex Prompt
Migrate chat eval harness for full rewrite:
- Unify all chat gates with graph metadata.
- Add legacy-vs-graph parity checks and sampled diffs.
- Enforce baseline governance and CI fail-fast behavior.

---

## Implementation Update (Bundle 1)

- Strengthened parity eval output for actionable triage:
  - added mismatch sample extraction with classification (`primary_diff_type`, `intent`, `topic`, `trace_id`, `request_id`)
  - added mismatch classification aggregates in derived report payload
- Expanded baseline governance checks in parity/matrix eval:
  - optional baseline approval metadata enforcement (`approved_by`, `approved_at`, `evidence`)
  - optional baseline age gate (`max_baseline_age_days`)
  - parity baseline drift now includes `ACTION_DIFF` ratio regression guard
  - matrix baseline drift now checks critical gate pass regression (`contract_compat`, `reason_taxonomy`, `parity`)
- Added v1 baseline fixtures for deterministic CI:
  - `services/query-service/tests/fixtures/chat_graph_parity_eval_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_eval_matrix_baseline_v1.json`
- Updated `RUN_CHAT_ALL_EVALS=1` flow:
  - `scripts/test.sh` now wires parity + matrix baseline files by default and enables baseline approval gate by default
  - CI contract/spec step now includes `RUN_CHAT_ALL_EVALS=1`
