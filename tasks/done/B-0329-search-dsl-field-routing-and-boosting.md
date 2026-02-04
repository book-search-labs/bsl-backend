# B-0234 — Search Service: QC 기반 필드 라우팅/부스팅 (ISBN/Author/Title/Series) + filters foundation

## Goal
- SR의 lexical query를 “그냥 multi_match”에서 업그레이드:
  - ISBN이면 keyword term query 우선
  - author/title/series/publisher면 해당 필드 boost
  - fallback은 multi_match 유지
- 향후 UI 필터를 위한 filter 처리 뼈대를 정리한다.

## Why
- 저자 검색/ISBN 검색 품질 개선의 최소 단위

## Scope
### In scope
- QC detected/understanding 기반 분기
- OS DSL 생성 로직 확장
- 기존 방식 fallback 유지

### Out of scope
- 벡터 모델 변경
- cross-encoder 개선

## DSL 예시
ISBN:
```json
{
  "query": {
    "bool": {
      "should": [
        { "term": { "isbn13.keyword": "978..." } },
        { "term": { "isbn10.keyword": "..." } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

Author + residual:
```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "authors.name_ko": { "query": "김영하", "boost": 3.0 } } }
      ],
      "should": [
        { "multi_match": { "query": "데미안", "fields": ["title_ko^2", "series_name", "publisher_name"] } }
      ]
    }
  }
}
```

## Acceptance Criteria
•	ISBN 입력에서 term 기반 쿼리 생성
•	author 입력에서 author 필드가 가장 강하게 매칭되도록 boost
•	기존 free text는 multi_match fallback

## Test plan
•	DSL snapshot 테스트(가능하면)
•	smoke: isbn/author/title

