# Kafka Schema Strategy (v1)

This project uses **Protobuf (proto3)** as the schema source of truth for Kafka events.
Schema files live under `contracts/events/` and are versioned with a `vN` suffix.

## 1) Envelope
Outbox relay publishes JSON envelopes with consistent metadata:

```json
{
  "schema_version": "v1",
  "event_id": "123456",
  "event_type": "search_impression",
  "dedup_key": "<sha256>",
  "occurred_at": "2026-01-31T00:00:00Z",
  "producer": "outbox-relay",
  "aggregate_type": "search",
  "aggregate_id": "imp_...",
  "payload": { "...": "..." }
}
```

- `payload` matches the fields defined in `contracts/events/*.proto`.
- Kafka key = `dedup_key` (idempotency key).

## 2) Compatibility rules (minimum)
- **Backward compatible by default** (consumers should tolerate new optional fields).
- **No field deletion or semantic changes** in the same version.
- **Additive changes only** (new optional fields allowed).
- **Breaking change** → create a new schema file (`*_v2.proto`) and a new topic.
- **Enum expansion**: allowed, never reuse old numeric values.

## 3) DLQ policy
- Producers/consumers retry with backoff.
- After N failures, route to a DLQ topic: `<topic>.dlq`.
- DLQ payload includes original topic + error context.

## 4) Replay strategy
- Source of truth for replay is `outbox_event`.
- Use `scripts/outbox/replay_outbox.py` to reset events to `NEW` for reprocessing.

Example:
```bash
python3 scripts/outbox/replay_outbox.py --status FAILED --event-type search_click --limit 500
```

## 5) v1 event schemas
- `contracts/events/search_impression.v1.proto`
- `contracts/events/search_result_summary.v1.proto`
- `contracts/events/search_click.v1.proto`
- `contracts/events/search_dwell.v1.proto`

## 6) Relay topic defaults (local)
- `search_impression` → `search_impression_v1`
- `search_result_summary` → `search_result_summary_v1`
- `search_click` → `search_click_v1`
- `search_dwell` → `search_dwell_v1`
- `ac_impression` → `ac_impression_v1`
- `ac_select` → `ac_select_v1`
