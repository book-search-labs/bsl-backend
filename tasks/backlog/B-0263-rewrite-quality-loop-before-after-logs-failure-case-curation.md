# B-0263 — QS Rewrite Quality Loop (before/after logging + failure curation)

## Goal
QS’ spell/rewrite/understanding quality can be improved by “operating loop”,
New *Compared log** and **Secret Case Curation** Creates pipeline.

- Track rewrite/spell actually helps(0→>0, improve score)
- Enable reproduction/analysis (A-0124 linkage) by collecting failure cases

## Background
- LLM/T5 outputs “like”, but can also spoil the search quality
- Quality improvement must:
  - (1) Record/after application
  - (2) Collect failure
  - (3) Modify rules/prompt/model
  - (4) You need a cycle to stop again with regression test

## Scope
### 1) Compare log schema (DB or OLAP)
- Table (Ticket: MySQL)   TBD   (v1)
  - `id` PK
  - `request_id`, `trace_id`, `session_id?`
  - `q_raw`, `q_norm`, `canonicalKey`
  - `reason` (ZERO_RESULTS/LOW_CONFIDENCE/HIGH_OOV)
  - `decision` (RUN/SKIP), `strategy`
  - `spell`: { q_spell, conf, method }
  - `rewrite`: { q_rewrite, conf, method }
  - `final`: { q_final, strategy }
  - `before`: { total_hits, top_score, score_gap }
  - `after`: { total_hits, top_score, score_gap }
  - New  TBD  : boolean (SR adopted)
  - `failure_tag`: enum (if any)
  - timestamps

> before/after values are callbacked to QS,
> SR is self-directed to   TBD   and can be used as request id.
> (Indeed, the SR side log is more natural, and QS is left around the "life information")

### 2) Failure curation rules (v1)
Automatic Tagging:
- `NO_IMPROVEMENT`: after.total_hits == 0 or top_score not improved
- New  TBD  : Editing Distance Transitions / Total Transformation
- New  TBD  : Author/Title moved to another entity (simplified humorous)
- New  TBD  : SHIMA MI JUNIOR
- `TIMEOUT`: stage timeout
- New  TBD  : skip to gating
- `LOW_CONF_OUTPUT`: conf below threshold

### 3) Export for Admin replay
- API(Internal) that allows you to pull the shield case TopN
  - `/internal/qc/rewrite/failures?from=...&limit=...`
- Enable reproduction in A-0124 Playground as payload

## Non-goals
- Admin UI implementation(A-0124)
- Offline eval revolving(B-0295) (but used as the seed of failure set)

## DoD
- When running rewrite/spell, the minimum log required before/after comparison is left
- failure tag is automatically filled (more than 5 basics)
- can generate replay payload recreated with request id
- You can calculate “rewrite accept rate”

## Observability
- metrics:
  - qs_rewrite_attempt_total{strategy}
  - qs_rewrite_accept_total
  - qs_rewrite_failure_total{failure_tag}
- dashboards:
  - accept_rate, no_improvement_rate, timeout_rate

## Codex Prompt
Build QS rewrite quality loop:
- Create query_rewrite_log table (or equivalent) and write logs on enhance.
- Add automatic failure tagging rules.
- Provide internal API to list failure cases and export replay-ready payload.
- Add metrics for attempt/accept/failure by tag.
