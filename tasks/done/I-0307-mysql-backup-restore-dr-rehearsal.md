# I-0307 — MySQL 백업/복구 + DR 리허설 스크립트

## Goal
canonical DB(MySQL)를 대상으로
- 정기 백업
- 복구 절차
- DR(재해복구) 리허설
  을 **스크립트 + 런북**으로 갖춘다.

## Why
- 데이터 파이프라인/운영에서 DB는 단일 실패 지점이 되기 쉬움
- “복구가 되는지”는 해보기 전엔 모름 → 리허설이 핵심

## Scope
### 1) 백업 방식(v1)
- 로컬/스테이징:
  - `mysqldump` (스키마+데이터) 또는
  - `mysqlpump` / `xtrabackup`(가능하면)
- 보관:
  - 로컬 파일 + (선택) 오브젝트 스토리지 업로드

### 2) 복구 절차(v1)
- 새 MySQL 인스턴스에 restore
- Flyway migration 재적용(필요 시)
- 앱 연결 확인 + smoke test

### 3) DR 리허설
- 월 1회(또는 릴리즈 전):
  - 백업 파일로 새 컨테이너에서 복원
  - 핵심 쿼리/인덱스/검색 스모크 테스트 통과

### 4) 자동화/검증
- backup 결과 파일 checksum
- 백업 성공/실패 알림(간단 로그/메트릭)

### 5) 문서
- `docs/DR_MYSQL.md`: 백업/복구/리허설 step-by-step

## Non-goals
- 멀티리전/멀티AZ 복제(초기엔 과함)
- PITR(시점복구) 완성(추후 binlog 기반으로 확장 가능)

## DoD
- 백업 스크립트가 실행되어 아카이브 생성 + 보관됨
- 복구 스크립트로 새 DB에 정상 복원 가능
- DR 리허설 체크리스트 + smoke test 커맨드가 문서화됨
- 최소 1회 리허설 실행 기록(로그/메모)

## Codex Prompt
Add MySQL backup/restore + DR rehearsal:
- Provide scripts for backup (dump/backup tool) and restore into a fresh instance.
- Include checksum verification and retention rules.
- Write a DR runbook with a rehearsal procedure and smoke tests.
- Validate by performing a restore locally and confirming app queries succeed.
