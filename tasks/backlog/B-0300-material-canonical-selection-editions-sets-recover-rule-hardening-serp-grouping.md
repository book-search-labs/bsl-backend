# B-0300 — Material 대표 선정(판본/세트/리커버) 룰 고도화 + SERP 그룹핑

## Goal
같은 “작품/시리즈”가 판본/리커버/세트/재출간으로 여러 문서로 존재할 때,
- 검색 결과에서 **중복 노출을 줄이고**
- 사용자에게 **대표(Primary) + 변형(Variants)** 구조로 보여준다.

## Why
- 지금 상태로는 “같은 책이 여러 번 보이는” 문제가 UX/CTR/랭킹 학습 모두를 망친다.
- Authority/merge는 검색 품질 고도화에서 체감이 가장 큼.

## Scope
### 1) Canonical key 설계(작품 단위)
- `work_key` 생성 규칙(초기 heuristic):
  - normalize(title) + normalize(main_author) + (series_key optional)
  - volume 정보는 work_key에 포함/미포함 정책 명확화(권차는 시리즈 내 항목)
- DB에 저장:
  - `material.work_key`, `material.work_key_confidence`

### 2) Merge/Group 모델
- `material_group`(대표) + `material_variant`(변형) 테이블(또는 material_merge 확장)
- 대표 선정 룰:
  - 판매중/재고/최신발행/메타 충실도(cover, description) + popularity 가중
- 변형 분류:
  - cover/edition/publisher/format(양장/전자책) 등

### 3) Index 반영 & SERP 그룹핑
- books_doc에:
  - `work_key`, `is_primary`, `primary_doc_id`, `variant_count`
- SR에서:
  - 기본 검색은 `collapse by work_key` (가능 시 OS field collapsing)
  - 또는 post-process로 work_key 기준 dedup 후 variants attach

### 4) Book detail 확장(대표/변형 노출)
- `/books/:id`에서:
  - primary + variants 리스트 제공(링크/차이점)

## Non-goals
- 완전 ML 기반 entity resolution
- 모든 케이스를 완벽히 병합(초기엔 “중복 최악”만 개선)

## DoD
- work_key가 생성되고(ETL 또는 배치) DB/Index에 반영된다
- 검색 결과에서 동일 work_key 중복 노출이 의미 있게 감소한다
- 대표/변형을 book detail에서 확인 가능하다
- 룰/우선순위가 문서화되고 회귀 테스트(샘플 쿼리)로 고정된다

## Codex Prompt
Implement authority grouping for materials:
- Create work_key heuristic and persist it to canonical DB.
- Build primary/variant grouping and selection rules (metadata completeness + popularity).
- Reflect grouping fields in OpenSearch and implement SERP dedup/collapse by work_key.
- Extend book detail to show variants and document rules + regression sample queries.
