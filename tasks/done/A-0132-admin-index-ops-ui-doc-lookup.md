# A-0132 — Admin Index Ops UI (Doc Lookup)

## Goal
Admin에서 doc_id/ISBN/키워드로 OpenSearch 문서를 빠르게 조회하고, 원본 문서/필드 확인 및 디버깅을 지원한다.

## Background
- `/ops/index/doc-lookup` 페이지가 현재 Placeholder 상태.
- 운영 중 특정 문서가 검색되는 이유/필드값 확인이 필요.

## Scope
- 조회 입력 폼
  - doc_id (필수), 추가 옵션: index/alias 선택, raw JSON 보기
- 결과 패널
  - _source 요약 카드 + raw JSON
  - 주요 필드 강조 (title, authors, publisher, issued_year, edition_labels)
- 실패 상태
  - not_found / timeout / error 메시지 표시

## API (BFF)
> 신규 API 필요. 계약/스키마는 별도 PR에서 정의.
- `GET /admin/ops/index/doc-lookup?doc_id=...&index=...`

## DoD
- doc_id 기준으로 문서를 즉시 확인 가능
- raw JSON / 요약 필드 모두 제공
- 에러/로딩 상태 UX 제공

## Codex Prompt
Admin(React)에서 Doc Lookup UI를 구현하라.
문서 ID로 검색하고, 요약 카드와 raw JSON 뷰를 제공하며, BFF API를 호출해 데이터를 표시하라.
