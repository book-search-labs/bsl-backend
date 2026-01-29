# A-0122 — Admin Doc/Index Ops UI (upload/reindex/version/rollback)

## Goal
RAG 문서 및 인덱스 운영(업로드/재색인/버전/롤백)을 위한 Admin UI.

## Scope
- Document upload (PDF/MD/HTML 등 1~2종부터)
- ingestion job 실행/상태 확인
- docs index version list + active version 표시
- rollback(이전 버전 alias swap)

## API (BFF)
- `POST /admin/docs/upload`
- `POST /admin/docs/reindex`
- `GET /admin/docs/index-versions`
- `POST /admin/docs/rollback?version=...`

## DoD
- 업로드→청킹/인덱싱 job 실행→버전 확인→롤백까지 가능
- 모든 작업 감사로그 기록

## Codex Prompt
Admin에서 문서/인덱스 운영 UI를 구현하라.
업로드/재색인/버전/롤백 흐름을 제공하고 job_run과 연결해 상태를 보여줘라.
