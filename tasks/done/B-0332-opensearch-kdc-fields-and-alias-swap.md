# B-0237 — OpenSearch: KDC facet/filter 지원 필드 추가 + reindex/alias-swap

## Goal
- books_doc에 KDC 필드 추가:
  - kdc_code, kdc_edition, (선택) kdc_path_codes
- blue/green reindex + alias swap으로 안전 반영
- facet(집계) 가능하게 만든다.

## Scope
### In scope
- index template/mapping 업데이트
- index writer(or reindex job)에서 필드 채우기
- SR에서 kdc filter 기반(terms/prefix) 처리 기반 마련

## Acceptance Criteria
- [ ] kdc_code 필터 검색 가능
- [ ] terms aggregation으로 facet 추출 가능
- [ ] alias swap 후 기존 검색 정상
