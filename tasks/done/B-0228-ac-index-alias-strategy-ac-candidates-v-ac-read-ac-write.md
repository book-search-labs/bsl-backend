# B-0228 — Autocomplete Index/Alias Strategy (ac_candidates_v*, ac_read/ac_write)

## Goal
Autocomplete 운영을 위해 OpenSearch 인덱스를 **버전 + alias**로 표준화한다.
- `ac_candidates_v*` (write target)
- `ac_read` / `ac_write` alias 분리
- reindex 중에도 serving 안정
- 집계 결과(CTR/popularity) 반영이 안전하게 가능

## Background
- AC는 p99이 빡세고, 인덱스 교체가 잦다.
- alias 없이 직접 인덱스에 붙으면:
  - 재색인/롤백 시 downtime
  - 운영중 mapping 변경 어려움

## Scope
### 1) Index set 정의
- `ac_candidates_v1` (mapping 고정)
  - fields:
    - `prefix` (keyword / edge_ngram 기반)
    - `suggest_text` (keyword/text)
    - `popularity_7d`, `ctr_smooth`
    - `updated_at`
    - (선택) `lang`, `kdc`, `category`
- Aliases:
  - `ac_read` → 현재 serving 인덱스
  - `ac_write` → 집계/업데이트 대상 인덱스

### 2) Write flow (2 patterns 중 1)
- Pattern A (권장: blue/green)
  - 새로운 `ac_candidates_v2` 생성
  - bulk load(기본 후보 + 집계 반영)
  - `ac_read` 스왑
  - old retention 후 삭제
- Pattern B (in-place update)
  - `ac_write`로 update/upsert
  - mapping 변경이 필요하면 결국 A로

### 3) Validation / smoke
- alias가 항상 하나의 인덱스를 가리킴
- read/write alias 꼬임 방지 체크

## Non-goals
- synonym/normalization 배포(=B-0224)
- Redis hot cache(=B-0229)

## DoD
- 템플릿/매핑과 alias 생성 스크립트가 존재
- ac_read/ac_write 전환(runbook 포함) 가능
- 롤백 절차 문서화(이전 버전 alias 복구)

## Observability
- index version tag 로그에 포함
- ac_read alias target을 dashboard/ops에서 확인 가능

## Codex Prompt
Define OpenSearch autocomplete index versioning + alias scheme:
- Create ac_candidates_v1 mapping + template.
- Create aliases ac_read and ac_write with safe swap scripts.
- Provide validation checks and rollback procedure in docs/runbook.
