# A-0120 — Web Admin: API 호출을 BFF로 전환(무중단)

## 목표
- Web Admin(5173)의 API 호출을 **BFF 단일 진입점**으로 점진 전환한다.
- Admin 기능(ops/reindex/policy/experiment/products 등) 전부가 최종적으로 BFF를 경유한다.
- 전환 과정에서 장애/지연 시 direct fallback으로 복구 가능(단, Admin은 보수적으로 적용).

## 범위(Scope)
- Admin이 호출하는 모든 서버 API를 BFF로 변경
  - Ops: job_run / ops_task / reindex 관련
  - Policies/Experiments
  - Catalog/Product(Phase 8 포함 시)
- 무중단 토글:
  - `VITE_ADMIN_API_MODE=bff_primary | bff_only`
  - direct fallback(선택): read-only 화면에 한해 허용, write/execute는 fallback 금지 권장

## 무중단 정책(권장)
- **READ 계열(list/detail)**: BFF 실패 시 direct fallback 허용
- **WRITE/EXECUTE 계열(reindex 실행/정책 변경/배포/롤백)**: fallback 금지
  - 이유: 운영 위험 작업은 항상 BFF의 Auth/RBAC/Audit/RateLimit을 거쳐야 함

## DoD
- [ ] Admin의 모든 API 호출이 BFF 우선
- [ ] read-only는 장애 시 fallback 가능, write/execute는 fallback 금지
- [ ] prod에서 direct-call 제거 가능
- [ ] Admin 위험 작업은 audit_log에 남는 경로로만 호출됨(B-0227 연동)

## Codex Prompt
Web Admin(5173)에서 모든 API 호출을 BFF로 무중단 전환하라.
- env toggle로 bff_primary/bff_only 모드를 제공하라.
- read-only 호출만 fallback 허용, write/execute는 fallback 금지로 구현하라.
- ops/policy/experiment/products 등 모든 API 호출을 API client 레이어로 통일하라.
- `.env.example`와 운영 전환/rollback 문서를 추가하라.
