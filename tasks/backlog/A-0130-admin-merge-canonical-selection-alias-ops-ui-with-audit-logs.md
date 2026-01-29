# A-0130 — Admin Authority/Merge Ops UI (material merge, agent alias)

## Goal
도서/저자 정합성(Authority)을 운영자가 관리할 수 있도록
- **material merge(판본/리커버/세트 중복 묶기 + 대표 선정)**
- **agent alias(저자 표기 변형 통합)**
- 변경 이력/감사 로그 기반으로 운영 UI 제공

## Background
- 대규모 LOD/NLK 데이터는 중복/표기 변형이 필연.
- 검색 품질(중복 노출/클릭 분산/CTR 왜곡)과 운영 안정성(LTR 피처) 모두에 치명적.

## Scope
### 1) Material Merge Ops
- 후보 탐지 결과 리스트(자동 생성 결과를 운영자가 확인)
  - title 유사도, isbn/issued_year, author overlap
- Merge group 상세
  - group 내 material 리스트
  - 대표(material_master_id) 선택
  - merge 이유/메모
- Action
  - merge 승인 / unmerge(롤백)
  - 대표 변경

### 2) Agent Authority Ops
- agent 후보 그룹(동명이인/표기변형)
  - 예: “김영하” vs “金英夏”
- alias mapping 관리
  - canonical_agent_id ← variants[]
- Action
  - alias 추가/삭제
  - canonical 변경(권한 필요)

### 3) Impact Preview (선택)
- merge/alias 적용 시:
  - SERP 그룹핑 변화(샘플 쿼리)
  - index reindex 필요 여부 표시

## Non-goals
- 자동 후보 생성 알고리즘 구현(B-0221b/B-0300/B-0301 영역)
- 실제 reindex job 실행 UI(A-0113)

## Data / API (via BFF)
- `GET /admin/authority/material/merge-candidates`
- `GET /admin/authority/material/merge-groups/{group_id}`
- `POST /admin/authority/material/merge-groups/{group_id}/approve`
- `POST /admin/authority/material/merge-groups/{group_id}/rollback`
- `GET /admin/authority/agent/candidates`
- `POST /admin/authority/agent/aliases`

## Persistence (suggested)
- material_merge_group(group_id, status, master_id, members_json, created_at)
- agent_alias(canonical_agent_id, alias_text, source, created_at)
- 모든 변경은 audit_log 기록

## Security / Audit
- merge/rollback/대표변경은 RBAC + audit_log 필수
- (옵션) 2인 승인 워크플로 확장 가능

## DoD
- 운영자가 중복 도서를 그룹화하고 대표 선정 가능
- 저자 표기 변형을 canonical로 묶을 수 있음
- 변경 이력/감사로그가 남고 롤백 가능

## Codex Prompt
Admin(React)에서 Authority/Merge 운영 UI를 구현하라.
Material merge candidates → group detail → approve/rollback/대표선정 흐름과,
Agent alias candidates → canonical 매핑 관리 화면을 제공하라.
BFF API만 호출하고 audit_log/RBAC 전제를 적용하라.
