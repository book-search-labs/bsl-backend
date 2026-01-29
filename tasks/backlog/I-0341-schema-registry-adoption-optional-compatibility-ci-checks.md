# I-0341 — Schema Registry Introduction (Optional) + Compatibility CI Inspection

## Goal
Manage events schema centrally,
Automatically perform compatibility tests at CI.

## Why
- The event is consumed “cross time”, so the schema compatibility is the core of operational stability
- DLQ/Replay

## Scope
### 1) Select Registry/Reality
- When choosing Avro: Confluent Schema Registry (or alternative)
- If you choose Protobuf: if you start with "File-based + CI compatibility check"
- endpoints/dev configuration by environment

### 2) compatibility rules
- Basic: BACKWARD or FULL (according to team/operation level)
- Breaking change definition (replacement/type change/requirement field, etc.)

### 3) CI Inspection
- In PR:
  - Check if the modified schema is compatible with the previous version
- About Us News
  - CI fail

### 4) Operation documents
- Schema versioning rules
- event producer/consumer release order guide (consumer first, etc.)

## Non-goals
- All services are immediately forced (to be introduced)

## DoD
- The search engine will work in a dev environment.
- schema compat check is performed in the CI, and fails when broken
- Versioning is applied for at least 3 event types

## Codex Prompt
Add schema registry & compatibility CI:
- Choose Avro+Schema Registry or Protobuf with version checks.
- Implement CI job that validates backward compatibility for changed schemas.
- Document schema evolution rules and producer/consumer rollout order.
