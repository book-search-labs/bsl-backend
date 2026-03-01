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
