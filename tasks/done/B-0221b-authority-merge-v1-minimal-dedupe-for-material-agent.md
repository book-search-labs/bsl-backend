# B-0221b — Authority/Merge v1 (material/agent dedup minimal set)

## Goal
NLK 기반 canonical 데이터에서 발생하는 **중복/표기 변형**을 “운영 가능한 최소 수준”으로 정리한다.
- **Material(도서) 중복 묶기**: 판본/리커버/세트/중복 레코드 후보를 그룹화
- **Agent(저자) 표기 변형 묶기**: 동일 인물로 보이는 표기 변형을 canonical로 매핑
- 검색 결과 중복 노출 감소 + CTR/피처 분산 방지(=LTR 성공 기반)

## Background
- LOD/대용량 ingest는 중복이 필연이고, 중복이 남아있으면:
  - SERP가 “같은 책”으로 도배됨 → UX/CTR 악화
  - 클릭/구매 로그가 분산됨 → 피처(ctr_smooth/popularity) 왜곡
  - LTR 라벨/피처 품질이 무너짐

## Scope (v1: minimal & deterministic)
### 1) Material merge 후보 생성(배치)
- 후보 규칙(초기):
  - (A) ISBN(가능하면) 동일 OR
  - (B) `title_norm + author_norm + issued_year` 근접 + 유사도(간단 토큰 Jaccard/Levenshtein) 기준
  - (C) series + volume 동일
- 결과: `material_merge_group`에 group 생성(OPEN 상태)

### 2) Master(대표) 선정 룰(v1)
- 기본 룰(가장 보수적):
  - ISBN-13 존재 > ISBN-10 존재 > issued_year 최신 > 메타 필드가 풍부한 것(title/subtitle/author/publisher/summary)
- master_id를 group에 기록

### 3) Agent alias 후보 생성(배치)
- 후보 규칙:
  - name_norm(공백/기호 제거) 동일
  - 한자/한글 병기(가능하면 사전 기반)
  - 생몰년/직업/관련 저작 overlap(있으면 가중)
- 결과: `agent_alias_candidate` 생성(OPEN)

### 4) “적용”은 분리 (중요)
- **v1에서는 자동 merge를 canonical에 바로 반영하지 않고**
  - (a) 후보 생성 + master 선정까지만 자동
  - (b) 운영 승인(A-0130) 후 반영(또는 승인 없으면 “검색단 그룹핑만” 우선)
- 반영 방식은 B-0300/B-0301(심화)에서 확장

## Non-goals
- 완전 자동 canonical rewrite(위험)
- 동명이인 disambiguation 정답화(추후)
- ML 기반 entity resolution(추후)

## Data Model (suggested)
- material_merge_group(group_id, status, master_material_id, members_json, rule_version, created_at)
- agent_alias_candidate(candidate_id, status, canonical_agent_id, variants_json, rule_version, created_at)
- agent_alias(canonical_agent_id, alias_text, source, created_at) — 승인 후 확정 테이블

## Interfaces / Jobs
- `job_type=AUTHORITY_CANDIDATE_BUILD`
- params:
  - since_date (증분)
  - rule_version
- outputs:
  - new groups, counts, sample preview

## Observability
- metrics:
  - authority_material_groups_created
  - authority_agent_candidates_created
  - approval_rate (admin 승인 후)
- logs:
  - rule_version, thresholds, sample pairs

## DoD
- 하루치 증분에 대해 후보 생성이 재실행 가능(idempotent)
- 후보 그룹/alias 후보가 DB에 쌓이고 샘플링 확인 가능
- master 선정 규칙이 문서화 + 재현 가능
- (선택) 검색단에서 group_id 기반 “중복 그룹핑”에 활용 가능

## Codex Prompt
Implement minimal deterministic authority/merge v1:
1) batch job to build material merge candidates + choose master
2) batch job to build agent alias candidates
   Persist results in tables with rule_version, idempotency, and metrics/logging.
   Do not automatically rewrite canonical; keep it approval-driven.
