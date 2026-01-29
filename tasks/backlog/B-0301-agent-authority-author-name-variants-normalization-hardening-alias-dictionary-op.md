# B-0301 — Agent authority(저자 표기 변형) 정규화 고도화 + alias 사전 운영화

## Goal
저자명이 “김영하/金英夏/Kim Young-ha”처럼 다양하게 표기되는 문제를 해결해
- 검색 매칭 안정화(title/author 필드)
- 중복 결과 감소
- 추천/랭킹 피처의 엔티티 정합성 개선

## Scope
### 1) Agent canonicalization
- `agent.canonical_name` 생성
- `agent_alias` 테이블 도입(또는 기존 구조 확장):
  - `agent_id`, `alias`, `alias_norm`, `source`, `confidence`, `created_at`

### 2) Alias 생성 로직(초기 규칙 기반)
- normalize rules:
  - NFKC/공백/구두점 제거, 영문 lower, 한자/한글 변환은 옵션
- 생성 소스:
  - NLK 원천 속성들(다국어 라벨)
  - 규칙 기반 변형(띄어쓰기/하이픈)
  - 운영자 수동 등록(Admin UI는 A-0130에서)

### 3) Search/Query 확장 사용
- QS:
  - detect “author intent” 시 alias 후보를 expand 힌트로 제공
- SR:
  - author 필드 검색 시 alias를 함께 매칭
- Index:
  - books_doc에 `author_aliases[]` 또는 `author_id` + join 전략(선택)

### 4) Quality guard
- 과확장 방지:
  - confidence 낮은 alias는 boost 낮게
  - 충돌(alias가 여러 agent로 매핑) 시 운영 큐로

## Non-goals
- 대규모 외부 authority DB 통합(VIAF 등) — 추후
- 완전 자동 disambiguation(동명이인 완벽 해결)

## DoD
- agent_alias가 생성/조회 가능
- author 검색에서 표기 변형 케이스가 개선됨(샘플 쿼리 회귀)
- 충돌/불확실 alias가 큐로 떨어지고 운영자가 확인 가능(A-0130 연결)

## Codex Prompt
Implement agent authority and alias dictionary:
- Add agent_alias table and canonical_name normalization rules.
- Generate aliases from source labels + heuristic variants, with confidence and collision handling.
- Use aliases in QS/SR for author-intent queries and update OpenSearch mapping accordingly.
- Add regression samples and a workflow for conflict review (to be wired to Admin UI later).
