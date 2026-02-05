# B-0307 — 사용자 데이터 export/delete (GDPR-lite, 포트폴리오 가점)

## Goal
사용자가 자신의 데이터를 **내보내기(export)** / **삭제(delete)** 할 수 있게 해서,
실서비스 운영 감성(privacy ops)을 갖춘다.

## Why
- “개인정보/사용자 데이터”를 다루는 서비스의 운영 필수 기능
- 포트폴리오에서 **신뢰/운영역량**을 크게 올려줌(정책/감사/삭제 플로우)

## Scope
### 1) 대상 데이터(초기 v1)
- user_profile(있다면)
- user_recent_query / recent_view
- user_saved_material / bookshelf
- user_preference / consent
- chat_history(선택), feedback logs(선택)
- orders/payments 등 커머스 데이터는 **삭제 대신 익명화/보관정책**으로 분리(선택)

### 2) API
- `POST /me/data/export` → export_job 생성
- `GET /me/data/export/:jobId` → 상태/다운로드 링크(또는 결과 payload)
- `POST /me/data/delete` → delete_job 생성(soft delete→hard delete 단계)
- `GET /me/data/delete/:jobId`

> BFF 단일 진입점 기준으로 구현(권장)

### 3) 처리 방식(비동기 Job)
- `job_run` 또는 별도 `privacy_job` 테이블로 상태 관리
- export 결과는:
  - v1: zip/json 생성 후 로컬 파일/오브젝트 스토리지에 저장
- delete는:
  - v1: 즉시 삭제 가능한 테이블부터 처리 + 로그 남김
  - v2: 보관정책/익명화 포함(커머스)

### 4) 보안/감사
- 본인 인증 필요(토큰 + 추가 확인 옵션)
- 모든 작업은 `audit_log`에 기록
- export 파일은 TTL/만료(예: 24h) 적용

## Non-goals
- 완전한 법무 수준 GDPR/CCPA 준수
- 커머스 결제/세금 데이터 삭제(대개 보관 필요) — v2에서 익명화/정책으로

## DoD
- export/delete 요청이 비동기로 실행되고 진행률/상태 조회 가능
- export 산출물이 사용자 단위로 정확하며 재시도해도 중복/오류 없음
- delete 후 사용자의 주요 기능 데이터가 실제로 제거됨(테스트로 검증)
- audit_log에 모든 요청/결과가 남음

## Codex Prompt
Implement user data export/delete:
- Add endpoints via BFF and implement job-based processing using job_run (or privacy_job).
- Export user data to JSON/ZIP with TTL and secure download.
- Delete user data safely with idempotency, audit logging, and clear status transitions.
- Add integration tests verifying export content and delete effectiveness.
