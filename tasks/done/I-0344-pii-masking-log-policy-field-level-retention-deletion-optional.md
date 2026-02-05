# I-0344 — PII 마스킹/로그 정책(필드 레벨) + 보관주기/삭제(선택)

## Goal
로그/이벤트/OLAP에 들어가는 개인정보(PII)를 제어하고,
보관주기/삭제 정책을 갖춘다(실서비스 감성 포인트).

## Why
- request/trace/log에 쿼리/세션/식별자가 섞이면 개인정보 리스크
- “관측성”과 “프라이버시” 균형이 운영력

## Scope
### 1) PII 분류/정책
- PII 후보:
  - user_id(가명), session_id, ip, user-agent, email/phone(향후)
  - chat prompt(특히 위험)
- 정책:
  - ip는 부분 마스킹/해시
  - user_id는 내부 surrogate key + 외부 노출 금지
  - chat prompt는 기본 저장 금지(옵션으로 샘플링/익명화)

### 2) 필드 레벨 마스킹
- structured logging에서 특정 필드 자동 마스킹
- Kafka/OLAP 적재 전에 PII 제거/해시화

### 3) 보관주기/삭제
- raw 로그 retention(예: 7~30일)
- OLAP는 집계/익명화 후 장기 보관
- 삭제 배치 잡(예: `delete_expired_logs`)

### 4) 문서화
- “어떤 데이터가 어디에 저장되는지” 데이터 맵
- 운영자 액션(삭제 요청/사고 대응)

## Non-goals
- 법적 컴플라이언스 전체(예: GDPR full) 완성(추후 확장)

## DoD
- 로그/이벤트에서 PII가 마스킹/제거됨(샘플 검증)
- retention job이 동작하고 지표/알람이 있음
- 데이터 맵 문서가 존재

## Codex Prompt
Add PII masking & retention:
- Define PII fields and implement field-level masking in logs and event pipelines.
- Add retention/deletion jobs for logs and raw data.
- Document a data map and verify with sampling tests.
