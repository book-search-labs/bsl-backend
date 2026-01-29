# B-0280 — RAG Ingest: Document collection/consuming/checking + change detection + deducting update

## Goal
RAG Chatbot is a global leader in RAG Chatbot.

- Input: PDF/HTML/Markdown/Text (MVP only)
- Output: regularization text + metadata in chunk units
- Core: **Change detection + Deletion Update**(json-ld ingest like “revisionable/early”)

## Background
- RAG is a quality “cleaning” soon.
- The operating type should be “how to put back when the statement changes”.
- Minimum request: doc id/version, chunk id stability, payload hash based test.

## Scope
### Document source model
- Document entity:
  - `doc_source(doc_id, source_type, uri/path, title, created_at, updated_at, source_hash, status)`
- Chongqing:
  - `doc_chunk(doc_id, chunk_id, heading_path, page, text, text_hash, order_no, meta_json, updated_at)`

### 2) Normalization(Required)
- Enrollment/Discovery
- heading structure conservation (when possible)
- Language Detection (ko/en) Tags

### 3) Chunking strategy (required)
- “Section-based + token length limit”
- chunk metadata:
  - `doc_id`, `chunk_id`, `title`, `heading_path`, `page`, `order_no`, `source_uri`, `updated_at`

### 4) Change detection & incremental(required)
- doc unit:
  - New  TBD  Change comparison detection
- chunk unit:
  - New  TBD  Removed chunk
- Home News
  - Same as the result when reissuing the input

### 5 days ) Job orchestration
-  TBD  
  - `job_type=RAG_INGEST`
  - Management Philosophy

## Non-goals
- Generating/Butter Indexing(=B-0281)
- LLM Call/Chat Orchestra(=B-0282)

## DoD
- Sample document set (e.g. 10 pieces) ingest success
- When one modified document update:
  - Change chunk is only updated and remaining
- chunk id Stable Rule Documentation
- job run Success / Shield Record + Error Report

## Codex Prompt
Build RAG ingest pipeline:
- Implement doc ingestion with normalization + section-based chunking and stable chunk_id rules.
- Add change detection using source_hash/text_hash and idempotent upserts, including removed chunk handling.
- Store doc_source and doc_chunk metadata and integrate with job_run for progress/error reporting.
