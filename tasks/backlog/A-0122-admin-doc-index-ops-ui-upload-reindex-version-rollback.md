# A-0122 — Admin Doc/Index Ops UI (upload/reindex/version/rollback)

## Goal
Admin UI for RAG document and index operation (upload/recolor/version/rollback).

## Scope
- Document upload (PDF/MD/HTML)
- ingestion job execution/check status
- docs index version list + active version display
- alias swap

## API (BFF)
- `POST /admin/docs/upload`
- `POST /admin/docs/reindex`
- `GET /admin/docs/index-versions`
- `POST /admin/docs/rollback?version=...`

## DoD
- Upload → Checking / indexing job execution → Confirming version → Rollback
- All Job AuditLog Records

## Codex Prompt
Implement the documentation/index operation UI in Admin.
Provide upload/recolor/version/rollback flow and show status by connecting job run.
