# I-0340 — Replay 도구(기간 지정 재처리) + DLQ 자동 라우팅

## Goal
Kafka 운영에서 “실패 메시지 재처리”를 제품 수준으로 만든다.
- DLQ로 떨어진 메시지를 안전하게 모아두고
- 기간/오프셋/키 기준으로 재처리(replay) 할 수 있게 한다.

## Why
- AC/Ranking/Chat/Commerce 모두 이벤트 기반 운영 루프라서,
  **DLQ + Replay 없으면 운영 중 개선/복구가 불가능**해짐.
- 스키마 변경/버그 수정 후 “과거 이벤트 재적용”은 필수.

## Scope
### 1) DLQ 표준
- DLQ 토픽 규칙: `{source_topic}.DLQ`
- DLQ payload 포함:
  - original_topic / partition / offset
  - event_id / dedup_key
  - error_type / error_message / stacktrace(요약)
  - failed_at / consumer_group / consumer_version

### 2) Replay CLI/Job
- 실행 형태(예시):
  - `replay --topic search_impression --from 2026-01-01 --to 2026-01-02 --group replay-search --dry-run`
  - `replay --dlq search_impression.DLQ --limit 10000 --dedup true`
- 옵션:
  - dry-run(출력만)
  - rate-limit(초당 N건)
  - key filter(dedup_key prefix 등)
  - re-publish target(원토픽/별도 replay 토픽)

### 3) Idempotency 연동
- consumer는 **dedup_key 기반 멱등 처리**(DB/Redis) 전제
- outbox_event(또는 processed_event) 테이블과 연동 가능

## Non-goals
- 완전한 데이터 백필 플랫폼(Flink/Spark)까지는 하지 않음

## DoD
- DLQ 라우팅이 기본 제공되고, 실패 메시지가 DLQ에 표준 포맷으로 적재됨
- replay 도구로 특정 기간 이벤트를 안전하게 재발행 가능
- rate-limit + dry-run + target 토픽 지정 지원
- 최소 1개 운영 시나리오(버그 수정 후 DLQ 재처리) 리허설 완료

## Codex Prompt
Implement Kafka DLQ + replay tooling:
- Standardize DLQ envelope fields.
- Provide a replay CLI/job supporting time-range, rate limit, dry-run, and target topic.
- Ensure idempotency via dedup_key and document operational runbook.
