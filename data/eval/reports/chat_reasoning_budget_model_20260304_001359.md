# Chat Reasoning Budget Model

- generated_at: 2026-03-04T00:13:59.682135+00:00
- policy_json: /Users/seungyoonkim/sideProjects/bsl/bsl-backend/var/chat_budget/budget_policy.json
- policy_total: 0
- missing_budget_field_total: 0
- invalid_limit_total: 0
- duplicate_scope_total: 0
- missing_sensitive_intent_total: 4

## Gate

- enabled: true
- pass: false
- baseline_failure: version_missing regression: baseline=0, current=1, allowed_increase=0
- baseline_failure: missing_sensitive_intent_total regression: baseline=0, current=4, allowed_increase=0
- baseline_failure: stale minutes regression: baseline=0.000000, current=999999.000000, allowed_increase=30.000000