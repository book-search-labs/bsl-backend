# B-0224 — Synonym/Normalization Deployment Pipeline (versioning + rollback)

## Goal
검색 품질에 직접 영향을 주는 **동의어/정규화 룰**을 운영형으로 배포한다.
- synonym_set을 DB로 버전 관리
- OpenSearch analyzer 반영(배포)
- 즉시 롤백 가능
- reindex 필요 여부를 판단/안내

## Background
- 동의어/정규화는 “코드 배포”보다 더 자주 바뀌고, 잘못 배포하면 검색이 망한다.
- 따라서 버전/롤백/검증이 필수

## Scope
### 1) Synonym Set Storage
- synonym_set(set_id, name, version, content_text, status, created_at)
- status:
  - DRAFT / ACTIVE / DEPRECATED
- 활성 버전은 1개(또는 alias)

### 2) Deployment Job
- steps:
  1) validate syntax(중복/루프/금칙어)
  2) upload to OpenSearch (synonyms API or file-based depending on setup)
  3) apply analyzer reload (가능하면 reload, 아니면 reindex 필요 표시)
  4) smoke query check(샘플 쿼리)
- 실패 시 이전 ACTIVE 유지

### 3) Rollback
- ACTIVE version pointer를 이전으로 되돌림
- analyzer reload or reindex 안내

### 4) Admin/Ops integration
- A-0107(정책 UI) or A-0113(ops)에서
  - 배포/롤백 트리거 가능(권한 필요)

## Non-goals
- 완전한 의미 기반 synonym 자동 생성
- multi-language synonym 고급(추후)

## Observability
- deploy status, duration, validation failures
- audit_log: 누가 어떤 버전을 활성화했는지

## DoD
- synonym 버전 생성 → validate → deploy → active 전환
- 롤백 버튼/명령으로 이전 버전 즉시 복구 가능
- 배포 실패 시 검색 서비스에 영향이 없도록 fail-safe

## Codex Prompt
Implement synonym/normalization deployment pipeline:
DB versioned synonym_set, validation, OpenSearch apply/reload, and rollback.
Ensure fail-safe behavior (keep previous ACTIVE on failure) with audit logs and metrics.
