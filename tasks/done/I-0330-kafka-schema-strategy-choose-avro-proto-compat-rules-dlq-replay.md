# I-0330 — Kafka 스키마 전략(Avro/Protobuf) + 호환성 규칙 + DLQ/Replay

## Goal
Kafka 이벤트를 “운영 가능한” 형태로 표준화한다:
- 스키마 버전/호환성(compatibility)
- DLQ/재처리(replay)
- 멱등키/중복 처리 가이드

## Why
- 이벤트는 시간이 지날수록 “예전 메시지”가 장애 원인이 됨
- AC/Ranking/Chat/Commerce까지 확장하면 스키마 관리 없이는 무조건 깨짐

## Scope
### 1) 스키마 포맷 선택
- Avro + Schema Registry(선택) 또는 Protobuf(권장)
- 최소 요구:
  - schema_version
  - event_id / dedup_key
  - occurred_at
  - producer/service name

### 2) 호환성 규칙(최소)
- backward compatible 기본
- breaking change 금지(필드 삭제/의미 변경 등)
- optional 필드 추가는 허용
- enum 확장은 규칙 정의

### 3) DLQ
- consumer 실패 시:
  - retry N회 + backoff
  - 이후 DLQ 토픽으로 이동
- DLQ 메시지에 오류 원인/스택/원본 오프셋 기록

### 4) Replay/Replayer
- 기간/오프셋 범위 지정 재처리 도구
- “멱등 처리” 전제:
  - outbox_event.dedup_key와 동일 기준으로 consumer에서 중복 처리

### 5) 문서/가이드
- 이벤트 타입 목록:
  - search_impression/click/dwell
  - ac_impression/ac_select
  - chat_feedback
  - admin_domain_event(ops/reindex/synonym/merge)
  - (추후) commerce events

## Non-goals
- 완전한 데이터 플랫폼(KStreams/Flink) 표준화(추후)

## DoD
- 최소 3개 이벤트 타입에 대해 스키마 파일이 존재(contracts/events/)
- consumer가 DLQ로 안전하게 떨어지고 replay가 가능
- 호환성 규칙이 문서화되고 CI에서 체크(가능하면)

## Codex Prompt
Define Kafka schema strategy:
- Choose Protobuf or Avro, create versioned schemas for core events.
- Implement DLQ handling and a replay tool.
- Document compatibility rules and enforce basic checks in CI.
