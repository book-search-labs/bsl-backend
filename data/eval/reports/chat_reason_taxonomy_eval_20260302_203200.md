# Chat Reason Taxonomy Eval Report

- generated_at: 2026-03-02T11:32:00.268024+00:00
- cases_source: services/query-service/tests/fixtures/chat_reason_taxonomy_cases_v1.json
- responses_source: services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json

## Summary

| Metric | Value |
| --- | --- |
| case_total | 7 |
| response_total | 4 |
| mismatch_total | 1 |
| invalid_total | 1 |
| unknown_total | 2 |
| invalid_ratio | 0.090909 |
| unknown_ratio | 0.181818 |

## Case Results

- ok_response: matched=true, invalid=false, unknown=false
- confirm_policy: matched=true, invalid=false, unknown=false
- auth_forbidden: matched=true, invalid=false, unknown=false
- provider_timeout_execute: matched=true, invalid=false, unknown=false
- forbidden_unknown: matched=true, invalid=true, unknown=false
- bad_format: matched=false, invalid=false, unknown=true
- source_violation: matched=true, invalid=false, unknown=true

## Response Results

- resp_ok: reason_code=OK, invalid=false, unknown=false
- resp_fallback_provider_timeout: reason_code=PROVIDER_TIMEOUT, invalid=false, unknown=false
- resp_confirm_required: reason_code=CONFIRMATION_REQUIRED, invalid=false, unknown=false
- resp_auth_forbidden: reason_code=AUTH_FORBIDDEN, invalid=false, unknown=false

## Gate

- pass: false
- failures:
  - taxonomy fixture mismatches: 1
  - invalid ratio exceeded: ratio=0.090909 > max=0.000000
  - unknown ratio exceeded: ratio=0.181818 > max=0.050000