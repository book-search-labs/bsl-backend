---
title: "30. Outbox Relay 심화: Envelope, Retry, DLQ, 재처리"
slug: "bsl-backend-series-30-outbox-relay-dlq-replay"
series: "BSL Backend Technical Series"
episode: 30
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 30. Outbox Relay 심화: Envelope, Retry, DLQ, 재처리

## 핵심 목표
Outbox Relay의 핵심은 Kafka 전송 자체보다, 실패를 통제 가능한 상태로 유지하는 것입니다.

핵심 구현 파일:
- `services/outbox-relay-service/src/main/java/com/bsl/outboxrelay/relay/OutboxRelayService.java`
- `services/outbox-relay-service/src/main/java/com/bsl/outboxrelay/config/OutboxRelayProperties.java`
- `services/outbox-relay-service/src/main/resources/application.yml`
- `scripts/outbox/replay_outbox.py`

## 1) 배치 루프 구조
`relayBatch()`는 주기적으로 실행되어

1. `fetchNewEvents(batchSize)`
2. 이벤트별 `publishWithRetry()`
3. 성공 ID는 `markSent`
4. 실패 ID는 `markFailed`

순서로 처리합니다.

## 2) 토픽 해상
`resolveTopic(eventType)`는 `topicMapping`에서 event_type별 토픽을 찾습니다.

매핑이 없으면 즉시 실패 처리하며, 잘못된 설정을 조기에 드러냅니다.

## 3) envelope 포맷
`buildEnvelope()`는 payload를 아래 공통 스키마로 감쌉니다.

- `schema_version=v1`
- `event_id`, `event_type`, `dedup_key`
- `occurred_at`
- `producer`
- `aggregate_type`, `aggregate_id`
- `payload`(원본 JSON)

소비자 입장에서 이벤트 메타와 비즈니스 payload를 분리해 읽기 쉽습니다.

## 4) retry 정책
`publishWithRetry()`는 `maxRetries`만큼 전송을 시도하고,
실패 시 `backoffMs * attempt`로 sleep합니다.

재시도 중 마지막 에러는 `lastError`에 저장됩니다.

## 5) DLQ 라우팅
재시도 소진 후 `dlqEnabled=true`면 원 토픽에 `dlqSuffix`를 붙인 토픽으로 전송합니다.

DLQ envelope에는 추가로
- `failed_at`
- `original_topic`
- `error`

를 기록합니다.

## 6) Kafka 헤더
`addHeaders()`가 아래 헤더를 주입합니다.

- `event_type`
- `event_id`
- `dedup_key`
- `aggregate_type`
- `aggregate_id`
- `topic`
- (`dlq`, `error` 선택)

소비자/관측 도구에서 헤더만으로도 분류가 가능합니다.

## 7) 기본 프로퍼티
`OutboxRelayProperties` 기본값:

- `enabled=true`
- `batchSize=200`
- `pollIntervalMs=1000`
- `maxRetries=3`
- `backoffMs=200`
- `dlqEnabled=true`
- `dlqSuffix=.dlq`

## 8) 이벤트 타입 매핑 예시
`application.yml`에는 기본적으로 아래 매핑이 있습니다.

- `search_impression`
- `search_click`
- `search_dwell`
- `ac_impression`
- `ac_select`
- `chat_request_v1`
- `chat_response_v1`
- `chat_feedback_v1`

## 9) 재처리 스크립트
`scripts/outbox/replay_outbox.py`는 outbox 상태를 `NEW`로 되돌려 재처리합니다.

필터:
- status
- event_type
- since/until
- limit
- dry-run

## 10) replay 동작 방식
스크립트는
1. 조건에 맞는 `event_id` 조회
2. `status='NEW', sent_at=NULL`로 update
3. commit

을 수행합니다.

즉, relay 애플리케이션 로직을 건드리지 않고 DB 상태만으로 재송신을 트리거합니다.

## 11) 로컬 점검 예시
```bash
python scripts/outbox/replay_outbox.py \
  --status FAILED \
  --event-type search_click \
  --limit 200
```

이후 relay 로그에서 해당 이벤트가 다시 발행되는지 확인합니다.

## 12) 구현상 의도
Outbox 패턴의 핵심은 "전송 성공"이 아니라 "전송 실패를 재시도 가능한 데이터로 남기는 것"입니다.

Relay + DLQ + replay 스크립트 조합은 이 요구를 로컬 환경에서도 완결된 루프로 제공합니다.
