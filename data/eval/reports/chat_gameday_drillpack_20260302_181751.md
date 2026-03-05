# Chat Gameday Drillpack

- generated_at: 2026-03-02T18:17:51.540182+00:00
- triage_file: /Users/seungyoonkim/sideProjects/bsl/bsl-backend/var/chat_graph/triage/chat_launch_failure_cases.jsonl
- triage_case_total: 0

## Top Reasons

- (none)

## Scenarios

### LLM timeout 급증 (gd-llm-timeout-surge)

- reason_hints: PROVIDER_TIMEOUT
- Detection
  - [ ] chat fallback ratio 및 PROVIDER_TIMEOUT reason 급증 확인
  - [ ] LLM gateway 응답시간(p95/p99)와 오류율 확인
- Mitigation
  - [ ] capacity guard를 DEGRADE_LEVEL_1 이상으로 상향
  - [ ] 필요 시 release train hold 및 canary stage 축소
- Validation
  - [ ] timeout reason 비율이 기준 이하로 복귀했는지 확인
  - [ ] commerce completion rate 회복 여부 확인
- Evidence
  - [ ] launch gate report
  - [ ] capacity/cost guard output
  - [ ] incident summary

### Tool 장애(조회/쓰기 API 실패) (gd-tool-outage)

- reason_hints: TOOL_FAIL, AUTHZ_DENY
- Detection
  - [ ] tool failure reason/top source 확인
  - [ ] action audit에서 실패 전이(FAILED_RETRYABLE/FAILED_FINAL) 점검
- Mitigation
  - [ ] tool retry budget/circuit breaker 상태 점검
  - [ ] 민감 write 경로를 fallback-safe 문구로 강등
- Validation
  - [ ] 중복 실행(idempotency 위반) 0건 확인
  - [ ] claim verifier 오탐/미탐 샘플링 검토
- Evidence
  - [ ] action audit log
  - [ ] triage queue sample
  - [ ] on-call action plan

### 근거부족 응답 급증 (gd-insufficient-evidence)

- reason_hints: insufficient_evidence
- Detection
  - [ ] insufficient_evidence_ratio 및 reason taxonomy 분포 확인
  - [ ] RAG/retrieval 경로의 source window 변화 확인
- Mitigation
  - [ ] query normalization/policy routing 임계치 재조정
  - [ ] fallback 템플릿/next_action 안내 문구 품질 점검
- Validation
  - [ ] insufficient ratio가 기준치 이하로 회복됐는지 확인
  - [ ] 사용자 후속 전환율(REFINE_QUERY/OPEN_SUPPORT_TICKET) 확인
- Evidence
  - [ ] launch metrics
  - [ ] reason taxonomy eval output
  - [ ] chat replay samples

### 비용/토큰 사용량 급등 (gd-cost-burst)

- reason_hints: budget_gate_failed
- Detection
  - [ ] LLM audit tokens/cost per hour 급등 확인
  - [ ] avg tool calls 및 llm path 비중 변화 확인
- Mitigation
  - [ ] capacity mode 상향(DEGRADE_LEVEL_1/2) 및 heavy path admission 제한
  - [ ] release hold 후 baseline 대비 변화량 점검
- Validation
  - [ ] cost/tokens per hour가 목표 범위로 복귀했는지 확인
  - [ ] 핵심 커머스 intent 완결률 저하가 없는지 확인
- Evidence
  - [ ] llm audit summary
  - [ ] capacity/cost guard report
  - [ ] readiness score report
