# B-0280 — RAG Ingest: 문서 수집/정규화/청킹 + 변경 감지 + 증분 업데이트

## Goal
RAG 챗봇을 위한 지식원천을 **운영형 파이프라인**으로 만든다.

- 입력: PDF/HTML/Markdown/Text (MVP는 1~2종만)
- 출력: chunk 단위의 정규화 텍스트 + 메타데이터
- 핵심: **변경 감지 + 증분 업데이트**(json-ld ingest처럼 “재실행 가능/멱등”)

## Background
- RAG는 “청킹”이 곧 품질이다.
- 운영형은 “문서가 바뀌었을 때 다시 넣는 방법”이 있어야 한다.
- 최소 요구: doc_id/version, chunk_id 안정성, payload_hash 기반 증분.

## Scope
### 1) Document source model(필수)
- 문서 엔티티:
  - `doc_source(doc_id, source_type, uri/path, title, created_at, updated_at, source_hash, status)`
- 청크 엔티티:
  - `doc_chunk(doc_id, chunk_id, heading_path, page, text, text_hash, order_no, meta_json, updated_at)`

### 2) Normalization(필수)
- 인코딩/개행/공백 정리
- heading 구조 보존(가능하면)
- 언어 감지(ko/en) 태그

### 3) Chunking strategy(필수)
- “섹션 기반 + 토큰 길이 제한”
- chunk metadata:
  - `doc_id`, `chunk_id`, `title`, `heading_path`, `page`, `order_no`, `source_uri`, `updated_at`

### 4) Change detection & incremental(필수)
- doc 단위:
  - `source_hash` 비교로 변경 감지
- chunk 단위:
  - `text_hash` 비교로 upsert/삭제(removed chunk 처리)
- 멱등:
  - 동일 입력 재실행 시 결과 동일

### 5) Job orchestration(권장)
- `job_run`과 연계:
  - `job_type=RAG_INGEST`
  - 진행률/오류 수집

## Non-goals
- 임베딩 생성/벡터 인덱싱(=B-0281)
- LLM 호출/챗 오케스트레이션(=B-0282)

## DoD
- 샘플 문서 세트(예: 10개) ingest 성공
- 변경된 문서 1개 업데이트 시:
  - 변경된 chunk만 업데이트되고 나머지는 유지
- chunk_id 안정 규칙 문서화
- job_run에 성공/실패 기록 + 에러 리포트

## Codex Prompt
Build RAG ingest pipeline:
- Implement doc ingestion with normalization + section-based chunking and stable chunk_id rules.
- Add change detection using source_hash/text_hash and idempotent upserts, including removed chunk handling.
- Store doc_source and doc_chunk metadata and integrate with job_run for progress/error reporting.
