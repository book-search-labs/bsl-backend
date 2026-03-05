# Chat Reason Taxonomy Eval Report

- generated_at: 2026-03-02T11:32:49.472780+00:00
- cases_source: services/query-service/tests/fixtures/chat_reason_taxonomy_cases_v1.json
- responses_source: services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json

## Summary

| Metric | Value |
| --- | --- |
| case_total | 7 |
| response_total | 4 |
| mismatch_total | 0 |
| fixture_invalid_total | 2 |
| fixture_unknown_total | 1 |
| invalid_total | 0 |
| unknown_total | 0 |
| invalid_ratio | 0.000000 |
| unknown_ratio | 0.000000 |

## Case Results

- ok_response: matched=true, invalid=false, unknown=false
- confirm_policy: matched=true, invalid=false, unknown=false
- auth_forbidden: matched=true, invalid=false, unknown=false
- provider_timeout_execute: matched=true, invalid=false, unknown=false
- forbidden_unknown: matched=true, invalid=true, unknown=false
- bad_format: matched=true, invalid=true, unknown=false
- source_violation: matched=true, invalid=false, unknown=true

## Response Results

- resp_ok: reason_code=OK, invalid=false, unknown=false
- resp_fallback_provider_timeout: reason_code=PROVIDER_TIMEOUT, invalid=false, unknown=false
- resp_confirm_required: reason_code=CONFIRMATION_REQUIRED, invalid=false, unknown=false
- resp_auth_forbidden: reason_code=AUTH_FORBIDDEN, invalid=false, unknown=false

## Gate

- pass: true
- failures: none