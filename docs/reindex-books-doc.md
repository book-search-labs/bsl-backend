# Canonical → OpenSearch Reindex (Local)

This doc describes the **local-only** reindex flow that reads from the canonical MySQL schema and rebuilds the OpenSearch books index.

## What it does
- (선택) 기존 books_doc_* 인덱스와 alias(별칭)를 삭제합니다.
- infra/opensearch/books_doc_v2.mapping.json을 기반으로 새 books 인덱스를 생성합니다.
- Canonical 테이블(material, material_agent, agent, material_identifier, material_concept, concept, overrides/merges)을 읽습니다.
- 검색용 books 문서로 비정규화(denormalize)한 뒤, OpenSearch에 bulk 인덱싱합니다.
- 인덱스 문서 수(count)를 검증하고 몇 가지 샘플 쿼리를 실행합니다.

## Run (one command)
```bash
./scripts/reindex_books.sh
```

## Requirements
- OpenSearch가 http://localhost:9200에서 실행 중이어야 합니다.
- MySQL이 실행 중이며 Canonical 테이블에 데이터가 채워져 있어야 합니다.
- Python deps installed:
```bash
python3 -m pip install -r scripts/ingest/requirements.txt
```

## Environment knobs (optional)
- `OS_URL` (default `http://localhost:9200`)
- `BOOKS_DOC_ALIAS` (default `books_doc_write`)
- `BOOKS_DOC_READ_ALIAS` (default `books_doc_read`)
- `BOOKS_DOC_INDEX_PREFIX` (default `books_doc_v2_local`)
- `BOOKS_DOC_MAPPING` (default `infra/opensearch/books_doc_v2.mapping.json`)
- `DELETE_EXISTING` (default `1`) — delete `books_doc_*` indices before reindex
- `OS_BULK_SIZE` (default `1000`)
- `OS_RETRY_MAX` (default `3`)
- `OS_RETRY_BACKOFF_SEC` (default `1.0`)
- `MYSQL_HOST` (default `127.0.0.1`)
- `MYSQL_PORT` (default `3306`)
- `MYSQL_USER` (default `bsl`)
- `MYSQL_PASSWORD` (default `bsl`)
- `MYSQL_DATABASE` (default `bsl`)
- `MYSQL_BATCH_SIZE` (default `1000`)
- `REINDEX_FAILURE_LOG` (default `./data/reindex_books_failures.ndjson`)

## Output / Verification
The script prints:
- Bulk 진행 로그 (indexed X (failed Y))
- OpenSearch에서 조회한 최종 문서 수(count)
- 몇 가지 샘플 쿼리의 hit 수

실패 건은 REINDEX_FAILURE_LOG에 문서 ID와 오류 상세 정보와 함께 기록됩니다.

## Troubleshooting
- **OpenSearch**에 접속할 수 없음: ./scripts/local_up.sh가 실행 중인지 확인하세요.
- **Count가 0**: canonical 테이블에 데이터가 있는지 확인하세요.  (`SELECT COUNT(*) FROM material;`)
- **Bulk 오류**: REINDEX_FAILURE_LOG에서 특정 문서의 오류 내용을 확인하세요.
- **매핑 오류**: 매핑 파일이 존재하는지, 그리고 문서 필드와 매핑이 일치하는지 확인하세요.
