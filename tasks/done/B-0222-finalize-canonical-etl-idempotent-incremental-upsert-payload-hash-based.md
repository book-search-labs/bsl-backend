# B-0222 — Canonical ETL Idempotent Incremental Upsert (payload_hash)

## Goal
Raw → Canonical 변환 파이프라인을 **멱등 + 증분(upsert)** 으로 고정한다.
- 같은 배치를 여러 번 돌려도 결과가 동일해야 함
- 변경된 raw만 canonical에 반영해야 함(재처리 최소화)
- 대용량에서도 안정적으로 “중단/재개” 가능해야 함

## Background
- B-0221에서 canonical 적재가 동작해도, 운영에서는:
  - 재실행/리트라이/부분 실패가 매일 발생
  - “전체 재생성”은 비용이 너무 큼
- 그래서 payload_hash 기반 변경감지가 필요

## Scope
### 1) payload_hash 계산 규칙 확정
- raw_node.payload(JSON)의 canonicalize(정렬/공백 제거) 후 SHA-256
- entity별 해시:
  - raw_node(payload_hash)
  - canonical row(source_hash) 저장

### 2) Change detection
- raw_node(node_id) 기준:
  - 신규: insert
  - 기존: payload_hash가 다르면 update
  - 같으면 skip
- batch 재실행 시 중복/불일치 0

### 3) Upsert 방식 표준화
- MySQL: `INSERT ... ON DUPLICATE KEY UPDATE`
- 업데이트 필드:
  - canonical payload fields
  - source_hash
  - updated_at
- “삭제”는 v1에서는 soft-delete 옵션(선택)

### 4) Checkpoint / resume
- ingest_checkpoint:
  - last_processed_node_id or last_offset
  - batch_id, entity_kind, processed_count
- 중단 시 재시작하면 checkpoint 이후부터 재개

## Non-goals
- 완전 CDC(바이너리 로그 기반)로 전환
- 다중 소스 통합(추후)

## Data Model impact (suggested)
- canonical tables: add `source_hash CHAR(64)` + `updated_at`
- ingest_checkpoint(entity_kind, cursor, batch_id, updated_at)

## Commands / Validation
- 동일 배치 2회 실행 → canonical row count/updated_at 변화가 “변경분만” 발생
- 랜덤 샘플 1k건:
  - raw payload_hash == canonical source_hash 확인

## Observability
- metrics:
  - etl_processed_total
  - etl_inserted_total
  - etl_updated_total
  - etl_skipped_total
  - etl_duration_ms
- logs:
  - batch_id, entity_kind, cursor range, error samples

## DoD
- 동일 입력 재실행 시 결과 동일(멱등)
- 변경된 raw만 canonical update(증분)
- checkpoint 기반 resume 가능
- 성능: 최소 “전체 대비 변경분 비율”에 비례하도록 동작

## Codex Prompt
Implement canonical ETL incremental upsert:
- compute payload_hash (stable canonicalization + sha256)
- detect changes vs canonical source_hash
- upsert only changed/new records
- persist checkpoints for resume
- add metrics/logging and deterministic DoD checks
