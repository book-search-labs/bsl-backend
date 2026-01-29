# I-0340 — Replay Tool (Re-processing) + DLQ Automatic Routing

## Goal
In Kafka operation, “Reprocessing of shield messages” is made of product level.
- Securely gather messages from DLQ
- Replay can be made based on period/offset/key.

## Why
- AC/Ranking/Chat/Commerce All events-based operating loops,
New *DLQ + Replay cannot be improved/restored during operation**
- After the change of the skimmer/bug fix, “Return event” is required.

## Scope
### 1) DLQ standard
- DLQ Topics:   TBD  
- DLQ payload included:
  - original_topic / partition / offset
  - event_id / dedup_key
  - error type / error message / stacktrace
  - failed_at / consumer_group / consumer_version

### 2) Replay CLI/Job
- Run Mode:
  - `replay --topic search_impression --from 2026-01-01 --to 2026-01-02 --group replay-search --dry-run`
  - `replay --dlq search_impression.DLQ --limit 10000 --dedup true`
- Testimonials News
  - dry-run(output only)
  - rate-limit
  - key filter(dedup key prefix)
  - re-publish target

### 3) Idempotency Integration
- consumer handles** (DB/Redis)
- outbox event(event event) can be integrated into the table

## Non-goals
- Flink/Spark

## DoD
- DLQ routing is based, and failed messages are loaded in standard format on DLQ
- Replay tool allows you to reissue certain period events safely
- rate-limit + dry-run + target
- Minimum 1 operation scenario (DLQ reprocessing after bug fixes) Rehearsal completed

## Codex Prompt
Implement Kafka DLQ + replay tooling:
- Standardize DLQ envelope fields.
- Provide a replay CLI/job supporting time-range, rate limit, dry-run, and target topic.
- Ensure idempotency via dedup_key and document operational runbook.
