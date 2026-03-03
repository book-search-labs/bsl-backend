# I-0360 — Chat LiveOps 강화 (온콜 안전망 + 릴리스 트레인)

## Priority
- P0

## Dependencies
- I-0351, I-0352, I-0353, I-0354, I-0355, I-0356
- B-0391, A-0150

## Goal
책봇 실서비스 운영 중 장애/비용/품질 리스크를 자동 감지하고, 릴리스 트레인 기반으로 안전하게 배포/롤백할 수 있는 인프라 운영체계를 완성한다.

## Scope
### 1) Release train and rollout guard
- 정시 릴리스 트레인(주간/긴급) 정책 수립
- canary/shadow 트래픽 승격 조건 자동화
- 컷라인 위반 시 즉시 fail-closed + 자동 rollback

### 2) On-call safety net
- 주요 알람(groundedness 급락, tool timeout 급증, 비용 급등) 룰 강화
- 알람→런북→조치→검증 자동 연결
- P1/P0 장애의 MTTA/MTTR 자동 집계

### 3) Capacity and cost resilience
- 모델/툴별 토큰/요청/비용 예산 캡
- 과부하 시 우선순위 큐 + load shedding + fallback 단계화
- 장애 중에도 핵심 커머스 의도는 우선 보존

### 4) Recovery and trust
- 재시작 후 세션 복구 무결성 점검
- 구성 드리프트 탐지 + immutable bundle 강제
- DR drill 정례화 및 결과 리포트 자동 저장

## DoD
- 릴리스 승격/차단/롤백이 자동 정책으로 동작
- 온콜 운영 지표(MTTA/MTTR/SLO) 안정화
- 비용 폭주/과부하 상황에서도 핵심 사용자 시나리오 유지
- 월간 DR 리허설 리포트 누적

## Codex Prompt
Harden chat live operations for production:
- Enforce release train gating with automatic rollback on gate breach.
- Build on-call automation from alert to runbook to validation.
- Add capacity/cost guardrails with priority-based degradation.
- Validate recovery integrity and immutable config bundle discipline.

## Implementation Update (2026-03-02, Bundle 1)
- [x] release train decision 스크립트 추가
  - `scripts/eval/chat_release_train_gate.py`
  - 입력: launch gate report + 현재 stage/dwell
  - 출력: `promote|hold|rollback` 및 next_stage/reason
- [x] auto rollback 연동 옵션
  - `--apply-rollback` 사용 시 canary controller override(`force legacy`) 적용
- [x] CI 진입점 추가
  - `RUN_CHAT_RELEASE_TRAIN_GATE=1 ./scripts/test.sh`

## Implementation Update (2026-03-02, Bundle 2)
- [x] LiveOps cycle 오케스트레이터 추가
  - `scripts/eval/chat_liveops_cycle.py`
  - launch gate 실행(또는 기존 리포트 입력) → release train decision → (옵션) rollback 적용을 단일 실행으로 제공
- [x] CI 진입점 추가
  - `RUN_CHAT_LIVEOPS_CYCLE=1 ./scripts/test.sh`

## Implementation Update (2026-03-02, Bundle 3)
- [x] LiveOps summary gate 추가
  - `scripts/eval/chat_liveops_summary.py`
  - 최근 cycle window에서 pass ratio/action 분포를 집계하고 gate fail 조건을 평가
- [x] CI 진입점 추가
  - `RUN_CHAT_LIVEOPS_SUMMARY_GATE=1 ./scripts/test.sh`

## Implementation Update (2026-03-02, Bundle 4)
- [x] LiveOps incident(MTTA/MTTR) gate 추가
  - `scripts/eval/chat_liveops_incident_summary.py`
  - cycle 리포트에서 incident open/resolve를 추적해 MTTA/MTTR 및 open incident 수를 게이트로 평가
- [x] CI 진입점 추가
  - `RUN_CHAT_LIVEOPS_INCIDENT_GATE=1 ./scripts/test.sh`

## Implementation Update (2026-03-02, Bundle 5)
- [x] On-call action plan 생성기 추가
  - `scripts/eval/chat_oncall_action_plan.py`
  - triage queue의 상위 reason/source를 요약해 즉시 조치 항목을 markdown/json으로 생성
- [x] CI 진입점 추가
  - `RUN_CHAT_ONCALL_ACTION_PLAN=1 ./scripts/test.sh`

## Implementation Update (2026-03-02, Bundle 6)
- [x] Capacity/Cost guard gate 추가
  - `scripts/eval/chat_capacity_cost_guard.py`
  - launch gate 성능 지표 + LLM audit 로그(error ratio/tokens/cost)로 `NORMAL|DEGRADE_LEVEL_1|DEGRADE_LEVEL_2|FAIL_CLOSED` 결정을 산출
  - 장애 상황에서도 커머스 핵심 intent 보존 우선순위를 출력
- [x] CI 진입점 추가
  - `RUN_CHAT_CAPACITY_COST_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-02, Bundle 7)
- [x] Immutable bundle drift guard 추가
  - `scripts/eval/chat_immutable_bundle_guard.py`
  - liveops cycle 리포트에서 release_signature 변경 추이를 분석해 누락/과도 변경/비허용 action 변경을 게이트로 차단
- [x] CI 진입점 추가
  - `RUN_CHAT_IMMUTABLE_BUNDLE_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-02, Bundle 8)
- [x] DR drill report 생성기 추가
  - `scripts/eval/chat_dr_drill_report.py`
  - liveops cycle에서 rollback drill/recovery/open drill/MTTR을 집계하고 json+markdown 리포트를 자동 저장
- [x] CI 진입점 추가
  - `RUN_CHAT_DR_DRILL_REPORT=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 9)
- [x] liveops summary/incident gate를 baseline 거버넌스형 리포트로 강화
  - `scripts/eval/chat_liveops_summary.py`
    - report JSON/Markdown 출력 + `--baseline-report` 회귀 비교
    - pass_ratio/failure_total/rollback_count drift guard 추가
  - `scripts/eval/chat_liveops_incident_summary.py`
    - report JSON/Markdown 출력 + `--baseline-report` 회귀 비교
    - MTTA/MTTR/open incident drift guard 추가
- [x] baseline fixture 추가
  - `services/query-service/tests/fixtures/chat_liveops_summary_baseline_v1.json`
  - `services/query-service/tests/fixtures/chat_liveops_incident_baseline_v1.json`
- [x] CI 진입점 확장
  - `scripts/test.sh`의 `RUN_CHAT_LIVEOPS_SUMMARY_GATE`, `RUN_CHAT_LIVEOPS_INCIDENT_GATE` 경로에서 baseline drift env 연결
