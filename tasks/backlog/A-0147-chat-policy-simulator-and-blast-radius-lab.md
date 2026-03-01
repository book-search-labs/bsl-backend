# A-0147 — Chat Policy Simulator + Blast-radius Lab

## Priority
- P2

## Dependencies
- A-0143, A-0144, B-0371

## Goal
정책 변경 전에 replay 샘플셋으로 영향범위(blast radius)를 시뮬레이션해 위험 변경을 사전에 차단한다.

## Scope
### 1) Policy simulation run
- 대상 정책 버전/비교 버전 선택
- replay 케이스셋 실행 후 결과 diff 생성

### 2) Blast-radius metrics
- 차단률 변화, 오탐/미탐 변화, 민감액션 경로 변화 지표
- 도메인/인텐트별 영향 분해

### 3) Decision support
- 위험 임계치 초과 시 배포 제한
- 승인/보류/롤백 추천 및 근거 표시

### 4) Artifact management
- 시뮬레이션 리포트 저장 및 이력 비교
- release evidence에 자동 첨부

## DoD
- 정책 변경 전 영향 시뮬레이션 루틴 정착
- 위험 정책 배포 사전 차단률 개선
- 승인 근거 데이터의 감사가능성 확보

## Codex Prompt
Build a policy simulation lab for chat governance:
- Run replay-based before/after comparisons of policy versions.
- Quantify blast radius by intent, safety, and commerce risk metrics.
- Gate risky policy rollouts with auditable decision evidence.
