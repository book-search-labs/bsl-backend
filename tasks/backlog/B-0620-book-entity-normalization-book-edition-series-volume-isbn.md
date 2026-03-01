# B-0620 — Book Entity Normalization v1 (Book/Edition/Series/Volume/ISBN)

## Priority
- P0

## Dependencies
- B-0601
- B-0261 (query normalize/detect)

## Goal
도서 도메인 핵심 엔티티를 정규화해 검색/추천/선택 메모리 참조 정확도를 끌어올린다.

## Why
- 동명 도서/판본/권차/ISBN 표기 흔들림이 멀티턴 오류의 주요 원인

## Scope
### 1) Normalization pipeline
- ISBN 하이픈/공백/13-10 변환
- 권차/시리즈 표기 파서
- edition variant canonicalization

### 2) Resolver contract
- 슬롯 추출 결과를 `book_id/edition_id/series_id/volume`로 정규화
- ambiguous match 시 confidence와 후보 반환

### 3) Catalog consistency
- 검색 index/doc canonical id 정렬
- alias dictionary 운영 포인트 정의

## DoD
- ISBN/권차/판본 정규화 정확도 기준 달성
- ambiguous entity는 execute로 가지 않고 disambiguation 경로로 이동
- selection memory 입력 ID 품질이 안정화된다.

## Interfaces
- query normalization layer
- search/recommend candidate payload

## Observability
- `chat_entity_normalize_total{type,result}`
- `chat_entity_ambiguous_total{type}`

## Test / Validation
- ISBN/권차 parser tests
- same-title disambiguation tests
- end-to-end selection stability tests

## Codex Prompt
Add robust book entity normalization:
- Normalize ISBN/edition/series/volume into canonical IDs.
- Return confidence and candidate set for ambiguous entities.
- Integrate normalized IDs into downstream selection logic.
