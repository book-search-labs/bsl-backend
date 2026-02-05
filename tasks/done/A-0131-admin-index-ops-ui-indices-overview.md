# A-0131 — Admin Index Ops UI (Indices Overview)

## Goal
Admin에서 OpenSearch 인덱스 현황(버전/alias/문서 수/상태)을 한눈에 확인할 수 있는 **Indices Overview** 화면을 제공한다.

## Background
- `/ops/index/indices` 페이지가 현재 Placeholder 상태.
- 운영 시점에는 alias 교체/버전 현황을 빠르게 확인해야 함.

## Scope
- 인덱스 리스트 테이블
  - index name, alias(읽기/쓰기), status, doc_count, size, created_at/updated_at(가능하면)
- alias 상태 요약 카드
  - books_doc / books_vec / ac_read / ac_write 등
- 인덱스 상세 drawer/modal
  - mapping JSON, settings JSON
  - 복사/다운로드 버튼

## API (BFF)
> 신규 API 필요. 계약/스키마는 별도 PR에서 정의.
- `GET /admin/ops/index/indices`
- `GET /admin/ops/index/aliases`
- `GET /admin/ops/index/{index}/mapping`
- `GET /admin/ops/index/{index}/settings`

## DoD
- 운영자가 alias 대상과 index 버전을 1분 내 확인 가능
- mapping/settings 확인 및 복사 가능
- 에러/로딩 상태 UX 제공

## Codex Prompt
Admin(React)에서 Indices Overview UI를 구현하라.
인덱스 리스트/alias 요약/매핑·설정 상세 보기(모달)를 제공하고, BFF API를 호출해 데이터를 표시하라.
