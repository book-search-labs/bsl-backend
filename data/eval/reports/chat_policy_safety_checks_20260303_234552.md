# Chat Policy Safety Checks

- generated_at: 2026-03-03T23:45:52.751434+00:00
- bundle_json: /Users/seungyoonkim/sideProjects/bsl/bsl-backend/var/chat_policy/policy_bundle.json
- rule_total: 0
- contradictory_rule_pair_total: 0
- missing_sensitive_guard_intent_total: 4
- unsafe_high_risk_allow_total: 0

## Gate

- enabled: true
- pass: false
- baseline_failure: missing_sensitive_guard_intent_total regression: baseline=0, current=4, allowed_increase=0