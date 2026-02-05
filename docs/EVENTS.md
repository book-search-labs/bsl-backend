# Events & Idempotency (Phase 10)

This document defines **event envelope standards** and **deduplication rules** for Kafka/outbox.

---

## 1) Event envelope (v1)

All outbox → Kafka events should follow the `outbox_envelope_v1.schema.json` shape:
- `schema_version`
- `event_id`
- `event_type`
- `dedup_key`
- `occurred_at`
- `producer`
- `aggregate_type`
- `aggregate_id`
- `payload`

The relay stamps these fields before publish.

---

## 2) Idempotency key standard (B-0305)

**Goal:** replays should be safe; consumers can drop duplicates.

**Recommended format:**
```
dedup_key = "{event_type}:{aggregate_type}:{aggregate_id}:{version_or_hash}"
```

Guidelines:
- **Stable per event**: same logical event yields same `dedup_key`.
- **Include version or hash** when payload is mutable.
- **Avoid timestamps** in the key (unless the event is time-sliced).

Examples:
- Search impression:
  - `search_impression:search:imp_abc123:v1`
- Order created:
  - `order_created:order:12345:v1`
- Refund processed:
  - `refund_processed:refund:98765:v1`

---

## 3) Schema registry (optional)

Schemas live under `schemas/events/`.
Run compatibility check in CI with:
```
RUN_SCHEMA_CHECK=1 ./scripts/test.sh
```

Breaking changes require a **new versioned schema file**.
