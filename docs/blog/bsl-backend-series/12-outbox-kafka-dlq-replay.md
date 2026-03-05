---
title: "12. Outbox Relay: Kafka 발행, DLQ, Replay"
slug: "bsl-backend-series-12-outbox-relay-kafka-dlq-replay"
series: "BSL Backend Technical Series"
episode: 12
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 12. Outbox Relay: Kafka 발행, DLQ, Replay

## 문제
도메인 트랜잭션과 Kafka 전송을 하나의 트랜잭션으로 묶기 어렵습니다. 이 프로젝트는 outbox_event + relay 루프로 분리했습니다.

핵심 구현:
- `services/outbox-relay-service/.../OutboxRelayService.java`
- `.../OutboxEventRepository.java`
- `.../OutboxRelayProperties.java`
- `scripts/outbox/replay_outbox.py`
- `schemas/events/outbox_envelope_v1.schema.json`

## 1) Relay 루프
`@Scheduled(fixedDelayString = "${outbox.relay.poll-interval-ms:1000}")`

루프 동작:
1. `status='NEW'` 이벤트 배치 조회(`event_id ASC`)
2. `publishWithRetry()`로 Kafka 전송
3. 성공: `markSent()` -> `SENT`
4. 실패: `markFailed()` -> `FAILED`

기본 송신 타임아웃은 `DEFAULT_SEND_TIMEOUT_MS=5000`.

## 2) 재시도와 DLQ
전송 실패 시 선형 backoff를 적용하고, 조건 충족 시 DLQ로 라우팅합니다.

- `dlqEnabled`
- `dlqSuffix` (기본 `.dlq`)

DLQ 레코드에도 원본 메타를 헤더로 같이 실어 재처리 근거를 남깁니다.

## 3) 이벤트 헤더 계약
relay는 헤더를 명시적으로 추가합니다.

- `event_type`
- `event_id`
- `dedup_key`
- `aggregate_type`
- `aggregate_id`
- (DLQ 시) `dlq=true`, `error`

이 값들은 consumer 쪽 멱등/분류 처리에 직접 사용됩니다.

## 4) Envelope 스키마
`outbox_envelope_v1.schema.json`로 payload wrapper shape를 고정했습니다. 이벤트 소비 서비스는 이 스키마 기준으로 파싱합니다.

## 5) Replay 도구
`scripts/outbox/replay_outbox.py`는 실패 이벤트를 다시 `NEW`로 되돌려 재전송합니다.

필터 옵션:
- `--status`
- `--event-type`
- `--since`, `--until`
- `--limit`
- `--dry-run`

실패 복구를 SQL 수작업이 아니라 반복 가능한 스크립트로 고정한 점이 중요합니다.

## 로컬 점검
```bash
# relay 메트릭 확인
curl -sS http://localhost:<outbox-relay-port>/internal/metrics | jq

# 실패 이벤트 dry-run replay
python scripts/outbox/replay_outbox.py --status FAILED --dry-run --limit 20
```

## 6) Relay 설정 기본값
`OutboxRelayProperties` 기본값:

1. enabled=true
2. batchSize=200
3. pollIntervalMs=1000
4. maxRetries=3
5. backoffMs=200
6. dlqEnabled=true
7. dlqSuffix=.dlq

로컬에서는 poll 간격과 batch 크기가 가장 체감 영향이 큽니다.

## 7) publishWithRetry 상세
각 이벤트 처리 흐름은 아래와 같습니다.

1. event_type -> topic 매핑 확인
2. envelope 직렬화
3. 최대 재시도 횟수만큼 전송 시도
4. 실패 시 backoff(`backoffMs * attempt`)
5. 최종 실패 시 DLQ 전송(활성화된 경우)

즉, 전송 실패를 즉시 폐기하지 않고 단계적으로 흡수합니다.

## 8) Envelope 필드 구조
일반 envelope와 DLQ envelope 모두 아래 공통 필드를 가집니다.

1. `schema_version=v1`
2. `event_id`, `event_type`, `dedup_key`
3. `occurred_at`, `producer`
4. `aggregate_type`, `aggregate_id`
5. `payload`

DLQ에는 `failed_at`, `original_topic`, `error`가 추가됩니다.

## 9) 로컬에서도 중요한 이유
relay를 분리해 두면 로컬에서도 아래를 독립 검증할 수 있습니다.

1. DB 트랜잭션 성공 여부
2. Kafka 전송 성공 여부
3. 재시도/실패 누적 동작
4. replay로 복구 가능한지

즉, 메시징 실패를 도메인 쓰기 실패와 분리할 수 있습니다.

## 10) replay 스크립트 활용 팁
1. 먼저 `--dry-run`으로 대상 건수를 확인합니다.
2. `--event-type`로 범위를 좁힙니다.
3. `--since/--until`로 시간 범위를 제한합니다.
4. `--limit`으로 대량 재전송을 제어합니다.

이 과정을 지키면 잘못된 대량 replay를 예방할 수 있습니다.
