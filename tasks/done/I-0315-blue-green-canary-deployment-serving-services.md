# I-0315 — Blue/Green/Canary 배포 (서빙 서비스)

## Goal
서빙 계층(BFF/QS/SR/AC/RS/MIS)을 대상으로
**무중단 배포(Blue/Green) + 점진 트래픽(Canary)** 전략을 운영 표준으로 만든다.

## Why
- 검색/랭킹/모델은 “품질/지연”이 민감 → 한번에 100% 배포는 위험
- Offline eval gate가 있어도, 실제 트래픽에서만 드러나는 문제가 존재

## Scope
### 1) Deployment 전략
- Blue/Green:
  - 동일 버전의 두 세트 운영(blue, green)
  - health/ready 확인 후 스위치
- Canary:
  - 일부 트래픽(예: 1%→5%→25%→100%)로 점진 확대
  - 에러율/latency/품질 프록시 기준으로 자동/수동 롤백

### 2) 라우팅 기준
- BFF 기준 canary:
  - header/cookie/user bucket
  - 또는 gateway 레벨에서 weight
- MIS/RS 모델 canary:
  - model_registry의 active + canary routing 정책(연계: B-0274)

### 3) 롤백 절차
- “이전 버전”으로 즉시 복귀 가능한 버튼/커맨드
- 롤백 시 관측 지표 확인 체크리스트 포함

## Non-goals
- 완전 자동화된 progressive delivery 플랫폼(추후)

## DoD
- stage에서 blue/green 전환이 실제로 동작(헬스체크 + 스위치)
- canary 라우팅(최소 2단계) 적용 가능
- 롤백 runbook 문서화 + 1회 리허설

## Codex Prompt
Add blue/green and canary deployment support:
- Define deployment manifests/scripts to run two versions and switch traffic safely.
- Implement canary routing strategy (weight or bucket) and rollback procedure.
- Document runbooks and verify in stage.
