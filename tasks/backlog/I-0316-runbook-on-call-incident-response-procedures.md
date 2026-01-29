# I-0316 — Runbook / On-call (Disability Procedure)

## Goal
When an error occurs during the operation, you can follow “Which look”
New *Runbook + On-call standard**

## Why
- The castle of the operation goes from the "return speed/consultation" than the code
- BSL has a lot of services, and it is complex to track the cause of failure.

## Scope
### 1) Common Runbook
- Incident triage:
  - 1) Symptom Classification(5xx/timeout/0-results/latency spike)
  - 2) Impact range (specific API? FAQs
  - (degrade mode, feature flag off, rerank off, hybrid off)
- Log/Trace Make Order:
  - end-to-end tracking with request id/trace id
- Rollback Procedure:
  - Distribution Rollback(I-0315 Link)
  - Model Rollback(B-0274 Link)
  - Index alias rollback(B-0223/0224)

### 2) Runbook by Scenario (min.)
- OpenSearch Disorder:
  - degraded(bm25-only, cached SERP)
  - query timeout tuning
- Kafka delay/DLQ increase:
  - outbox backlog processing
  - replayer execution(Phase 10/I-0340 connection)
- MIS Disorder:
  - rerank off → fusion result return
- ETL ETL /Index job failed:
  - job run confirmation → Ashdo → Snapshot/Restore(I-0308 Link)

### 3) On-call standard (simplified)
- Tag:
  - error rate, p99 latency, 0-results rate, outbox backlog, consumer lag
- Escalation:
  - Who/Any Order/Any Information Included

## Non-goals
- 24/7 Practical operation (Documentation center at Portfolio phase)

## DoD
- New  TBD  write
- Min. 3 Disability Scenario Rehearsal (Local/Stage)
- “Rerank/hybrid/2-pass” list and method included in the document

## Codex Prompt
Create operational runbooks:
- Write RUNBOOK.md covering triage, mitigation toggles, rollback steps, and service-specific failure playbooks.
- Include how to use request_id/trace_id across services.
- Add alarm thresholds and an on-call escalation checklist.
