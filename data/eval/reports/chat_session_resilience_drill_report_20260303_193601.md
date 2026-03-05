# Chat Session Resilience Drill Report

- generated_at: 2026-03-03T19:36:01.209043+00:00
- events_jsonl: /Users/seungyoonkim/sideProjects/bsl/bsl-backend/var/chat_governance/session_resilience_drills.jsonl
- window_size: 0
- success_ratio: 0.0000
- open_drill_total: 0
- avg_rto_sec: 0.0
- message_loss_ratio: 0.000000
- missing_required_scenarios: ['BROKER_DELAY', 'CONNECTION_STORM', 'PARTIAL_REGION_FAIL']

## Gate

- enabled: true
- pass: false
- baseline_failure: required scenario coverage regression: baseline_missing=0, current_missing=3, allowed_increase=0