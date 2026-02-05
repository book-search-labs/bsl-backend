# I-0312 — Audit Log 강제 + Admin 위험작업 승인(옵션) (Security/Ops)

## Goal
Admin이 수행하는 운영/정책/데이터 변경 작업에 대해
1) **감사로그(audit_log) 100% 적재**를 강제하고
2) (옵션) **위험 작업 2인 승인(dual-approval)** 흐름을 지원한다.

## Why
- “누가/언제/무엇을/왜”를 남기지 않으면 운영이 곧 사고로 이어짐
- reindex/merge/synonym 배포/권한 변경은 특히 위험 → 최소한 추적 가능해야 함

## Scope
### 1) Audit Log 강제(필수)
- 기록 대상(최소):
  - RBAC 변경(역할/권한)
  - Reindex/Index Ops 트리거
  - Synonym/Normalization 세트 변경/배포
  - Authority merge(대표 선정/병합)
  - 실험/모델 버전/정책 변경
  - (추후) Commerce 운영(환불/취소/재고 강제조정)
- 기록 필드(네 스키마 기준):
  - actor_admin_id, action, resource_type/resource_id
  - before_json/after_json (가능한 범위)
  - request_id/trace_id/ip/user_agent

### 2) “위험 작업” 분류/정책
- 위험 작업 리스트를 config로 관리:
  - e.g. `REINDEX_TRIGGER`, `ALIAS_SWAP`, `SYNONYM_DEPLOY`, `AUTHORITY_MERGE`, `RBAC_CHANGE`
- 위험 작업은 최소:
  - Admin RBAC 권한 + audit_log 기록은 필수

### 3) 2인 승인(옵션)
- 흐름:
  1) 요청자(Admin A)가 작업 요청 생성(상태: PENDING_APPROVAL)
  2) 승인자(Admin B)가 승인(상태: APPROVED) 후 실행
  3) 실행 결과 기록(SUCCESS/FAILED)
- 저장 방식(권장):
  - `ops_task`에 `approval_required`, `approved_by`, `approved_at` 필드 추가(또는 별도 approval 테이블)

### 4) UI 연계
- Admin UI(A-0113/A-0130 등)에서:
  - audit log 조회/필터
  - 승인 대기 목록/승인 버튼(옵션)

## Non-goals
- 완전한 SOX 수준의 통제(초기 범위 밖)
- 외부 SIEM 연동(추후)

## DoD
- BFF의 Admin write endpoint에서 audit_log 기록이 누락되지 않음(미들웨어/인터셉터로 강제)
- 위험 작업에 대해 “승인 필요” 옵션을 켜면 승인 없이 실행 불가
- audit log 조회 API + Admin 화면에서 조회 가능(최소)
- 샘플 시나리오 1개 이상 검증(예: reindex trigger → 승인 → 실행 → 로그 확인)

## Codex Prompt
Implement admin audit & optional dual-approval:
- Enforce audit_log writes for all admin mutating endpoints in BFF.
- Define a risk-action policy list and block risky actions unless approved (optional feature flag).
- Extend ops_task (or new table) to support approvals and track approver/ timestamps.
- Add minimal APIs + admin UI hooks to view logs and approve tasks.
