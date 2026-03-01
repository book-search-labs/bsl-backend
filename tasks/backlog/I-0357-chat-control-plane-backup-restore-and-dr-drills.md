# I-0357 — Chat Control-plane Backup/Restore + DR Drills

## Priority
- P1

## Dependencies
- I-0307, I-0308, I-0356, B-0371, B-0363

## Goal
챗 제어평면(정책 번들/세션 상태 메타/운영 설정)의 백업/복구 체계를 구축해 장애 시 빠르게 복구한다.

## Non-goals
- 백업 저장소 벤더를 전면 교체하지 않는다.
- 온라인 서비스 데이터 전부를 본 티켓에서 다루지 않는다(제어평면 중심).

## Scope
### 1) Backup coverage
- 정책 번들, tool registry, workflow config, 핵심 session metadata 백업
- 증분/전체 백업 정책 수립

### 2) Restore runbook
- 환경별 복구 절차(스테이징/프로덕션) 정의
- 복구 전 검증/복구 후 검증 체크리스트 자동화

### 3) DR drill automation
- 정기 복구 리허설 스케줄링
- RTO/RPO 측정 및 이력 보관

### 4) Safety and security
- 백업 암호화/접근제어
- 복구 권한 최소화 및 감사 로그

## Runbook integration
- 복구 절차를 `docs/RUNBOOK.md`와 단계별 링크
- drill 실패 원인별 대응 매뉴얼(권한/무결성/버전불일치) 연결

## Observability
- `chat_controlplane_backup_total{type,result}`
- `chat_controlplane_restore_total{env,result}`
- `chat_controlplane_dr_drill_total{result}`
- `chat_controlplane_rto_seconds`
- `chat_controlplane_rpo_seconds`
- `chat_controlplane_restore_validation_failed_total`

## Test / Validation
- 백업 무결성 검증 테스트
- 복구 시나리오 e2e 리허설 테스트
- 권한 없는 복구 시도 차단 테스트
- 복구 후 정책/세션메타 버전 일치성 검증 테스트

## DoD
- 제어평면 데이터 백업/복구 자동화 확보
- 정기 DR 드릴에서 목표 RTO/RPO 달성
- 복구 절차의 감사추적/보안 통제 확보
- drill 결과 리포트가 릴리즈 게이트 증빙으로 사용 가능

## Codex Prompt
Harden chat control-plane disaster recovery:
- Back up policy/config/state artifacts with encrypted storage and access controls.
- Automate restore drills and track RTO/RPO metrics.
- Provide runbook-driven verification before and after recovery.
