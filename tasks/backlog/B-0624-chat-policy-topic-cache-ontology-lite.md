# B-0624 — Chat Policy Topic Cache + Ontology-lite v1

## Priority
- P2

## Dependencies
- B-0603
- B-0609

## Goal
정책 질의를 토픽 키로 정규화해 캐시 효율을 높이고 근거 일관성을 유지한다.

## Why
- 문장 표면이 달라도 정책 토픽이 동일한 경우가 많아 토픽 캐시가 비용/지연에 유리

## Scope
### 1) Topic ontology-lite
- `RefundPolicy`, `ShippingPolicy`, `OrderCancelPolicy`, `EbookRefundPolicy` 등 토픽 표준화

### 2) Cache keying
- `topic_key + locale + policy_version` 기반 캐시
- 정책 버전 변경 시 자동 무효화

### 3) Safe fallback
- 토픽 미분류 시 일반 RAG 경로로 fallback
- low confidence는 캐시 미사용

## DoD
- 정책 FAQ 경로 캐시 hit율이 기준 이상 상승
- 정책 변경 이후 stale 응답이 노출되지 않는다.

## Interfaces
- policy classifier
- policy cache store

## Observability
- `chat_policy_topic_cache_hit_total{topic}`
- `chat_policy_topic_miss_total{reason}`

## Test / Validation
- topic classification tests
- policy version invalidation tests
- stale-cache regression tests

## Codex Prompt
Implement topic-oriented policy caching:
- Classify policy queries into ontology keys.
- Cache responses by topic+locale+policy version.
- Invalidate safely on policy updates.
