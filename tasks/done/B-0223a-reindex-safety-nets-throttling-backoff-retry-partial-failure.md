# B-0223a — Reindex Safety Guards (throttle/backoff/retry/partial failure)

## Goal
B-0223 Index Writer의 운영 안정성을 높이는 “안전장치”를 추가한다.
- 스로틀링(클러스터 보호)
- 백오프/재시도(일시 장애 복원)
- 부분 실패 처리(특정 배치 실패 시 건너뛰기/재처리)
- 안전한 중단/재개(체크포인트)

## Scope
### 1) Throttling
- bulk size, concurrency, refresh interval 정책
- cluster health(RED/YELLOW) 시 자동 slowdown

### 2) Backoff/Retry Policy
- transient errors(429/503/timeout) 지수 백오프
- max retries + DLQ(실패 레코드 저장) 옵션

### 3) Partial failure handling
- bulk response에서 실패한 item만 별도 큐에 저장
- 재시도 batch 재구성
- 실패 누적 임계치 초과 시 job FAILED 전환

### 4) Checkpoint
- cursor:
  - last_material_id / last_offset
- job_resume 시 checkpoint부터 재개

## Non-goals
- exactly-once indexing 보장(현실적으로 어려움)
- index-level transactional semantics

## Data
- reindex_job.progress_json에:
  - cursor, total, processed, failed, retries
- reindex_error(job_id, entity_id, reason, payload_hash, created_at) (선택)

## DoD
- OpenSearch 429/timeout 상황에서도 job가 자동 완화 + 재시도
- bulk 일부 실패 시 “전체 중단”이 아니라 재시도/누적 실패 정책으로 처리
- pause/resume 시 중복 인덱싱 최소화(멱등키/문서 id 기준)

## Codex Prompt
Enhance reindex job safety:
implement throttling based on cluster health, retry/backoff for transient errors,
partial failure tracking + retry queue, and checkpointed resume semantics.
