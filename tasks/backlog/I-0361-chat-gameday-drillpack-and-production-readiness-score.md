# I-0361 — Chat Gameday Drillpack + Production Readiness Score

## Priority
- P0

## Dependencies
- I-0360
- B-0391, A-0150

## Goal
책봇 실서비스 운영을 위해 월간 게임데이(장애 훈련)와 readiness score 체계를 표준화하여, 출시/운영 상태를 수치로 관리한다.

## Scope
### 1) Gameday drillpack
- 시나리오: LLM timeout 급증, tool 장애, 근거부족 폭증, 비용 폭주
- 시나리오별 탐지→조치→검증 체크리스트 템플릿화
- drill 결과를 리포트로 자동 저장

### 2) Readiness score
- 품질/안전/SLA/비용/복구성 지표를 가중합 점수로 관리
- 점수 임계치 미달 시 release hold
- 추세 기반 개선 목표(주/월) 설정

### 3) Incident feedback binding
- 실제 장애와 drill 케이스를 동일 taxonomy로 관리
- 사후 분석 결과를 다음 drill 시나리오로 자동 반영

## DoD
- 월간 drill이 누락 없이 수행되고 결과가 축적됨
- readiness score가 릴리스 의사결정에 실제 사용됨
- 주요 장애 유형에 대한 대응시간 지표 개선

## Codex Prompt
Operationalize chat reliability with gamedays:
- Create drillpacks for major failure classes and automate evidence capture.
- Compute a production readiness score and gate releases by threshold.
- Tie real incidents back into the next drill cycle.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Production readiness score 스크립트 추가
  - `scripts/eval/chat_readiness_score.py`
  - launch/liveops/incident/drill/capacity 신호를 가중합해 `READY|WATCH|HOLD` tier 및 `promote|hold` 권장 액션 산출
  - gate 모드에서 min_score 미달, blocker 존재, require_promote 위반 시 실패 처리
- [x] CI 진입점 추가
  - `RUN_CHAT_READINESS_SCORE=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Gameday drillpack 생성기 추가
  - `scripts/eval/chat_gameday_drillpack.py`
  - LLM timeout/tool outage/근거부족/비용폭주 시나리오별 Detection→Mitigation→Validation→Evidence 체크리스트를 markdown/json으로 자동 생성
  - triage top reasons를 reason_hints에 반영
- [x] CI 진입점 추가
  - `RUN_CHAT_GAMEDAY_DRILLPACK=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Incident feedback binding 스크립트 추가
  - `scripts/eval/chat_incident_feedback_binding.py`
  - liveops incident reason + triage reason을 공통 taxonomy(LLM_TIMEOUT/TOOL_OUTAGE/EVIDENCE_GAP/COST_BURST/...)로 매핑
  - bound category 집계와 drillpack 반영 권고안을 markdown/json으로 자동 생성
- [x] CI 진입점 추가
  - `RUN_CHAT_INCIDENT_FEEDBACK_BINDING=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Readiness trend gate 추가
  - `scripts/eval/chat_readiness_trend.py`
  - readiness score 리포트의 주/월 평균과 delta를 계산하고 다음 주/월 목표 점수를 자동 산출
  - gate 모드에서 min_reports/min_week_avg/min_month_avg 임계치 검증
- [x] CI 진입점 추가
  - `RUN_CHAT_READINESS_TREND=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 5)
- [x] Gameday readiness packet 스크립트 추가
  - `scripts/eval/chat_gameday_readiness_packet.py`
  - readiness/trend/drillpack/feedback/DR 리포트를 결합해 최종 상태(`READY|WATCH|HOLD`)와 권장 액션(`promote|hold`)을 산출
  - require-all 옵션으로 필수 증거 리포트 누락 차단
- [x] CI 진입점 추가
  - `RUN_CHAT_GAMEDAY_PACKET=1 ./scripts/test.sh`
