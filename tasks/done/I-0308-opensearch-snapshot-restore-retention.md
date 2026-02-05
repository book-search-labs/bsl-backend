# I-0308 — OpenSearch 스냅샷/복구 + retention (Index DR)

## Goal
OpenSearch 인덱스를 대상으로 **정기 스냅샷 + 복구 절차 + 보관(retention)** 을 운영 표준으로 확정한다.

## Why
- 인덱스는 재생성(reindex) 가능해도, 장애/실수/삭제에 대비한 “빠른 복구”가 필요
- alias/blue-green이 있어도, 스냅샷이 있으면 RTO(복구시간)가 크게 줄어듦

## Scope
### 1) Snapshot Repository 구성(v1)
- 로컬/스테이징: filesystem repository (컨테이너 볼륨 마운트)
- prod 확장: S3 repository (추후)

### 2) Snapshot 정책
- 스냅샷 대상:
  - `books_doc_*`, `books_vec_*`, `ac_candidates_*`, (RAG) `docs_*`
- 스냅샷 주기:
  - daily(또는 6h) + 릴리즈 전 수동 스냅샷
- include_global_state: false(권장, 운영 단순화)

### 3) Retention(보관)
- daily: 최근 7~14개
- weekly: 최근 4개(선택)
- 삭제 정책 자동화(스크립트/크론)

### 4) 복구 절차(Runbook)
- 신규 클러스터/새 노드로 restore
- alias 재연결(중요)
- 샤드/템플릿 확인 + smoke test

### 5) 검증/모니터링
- 스냅샷 성공률/시간
- restore 시나리오 1회 이상 리허설

## Non-goals
- 멀티리전 복제(초기 범위 밖)
- 완전 자동 failover(추후)

## DoD
- snapshot repo 생성 및 스냅샷/삭제 스크립트 존재
- `docs/DR_OPENSEARCH.md`에 복구 절차 문서화
- 최소 1회 restore 리허설 수행(로컬/스테이징)
- alias 기반 검색 스모크 테스트 통과

## Codex Prompt
Implement OpenSearch snapshot & restore:
- Create snapshot repository (filesystem for local/stage).
- Add scripts to create snapshots, list, delete old snapshots (retention).
- Write a runbook for restore and alias re-attach.
- Validate by snapshotting and restoring into a fresh OpenSearch instance.
