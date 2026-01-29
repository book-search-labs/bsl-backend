# B-0307 — User data export/delete (GDPR-lite, portfolio point)

## Goal
You can get your own data **export** / **delete**,
Copyright (c) 2018 SHINSEGAE. All Rights Reserved.

## Why
- “Privacy/User Data” for the operation of the service required
- In the portfolio, you can upload your trust/operation status** (Policy/Promotion/Promotion)

## Scope
### 1) Target data (Ultra v1)
- user profile()
- user_recent_query / recent_view
- user_saved_material / bookshelf
- user_preference / consent
- chat history(optional), feedback logs(optional)
- Customs data such as orders/payments are separated by anonymousization/retention policy** instead of deletion.

### 2) API
- New  TBD   → export job creation
- New  TBD   → status/download link (or result payload)
- New  TBD   → delete job creation (soft delete→hard delete step)
- `GET /me/data/delete/:jobId`

> Implemented as a single entry point for BFF

### 3) Processing Method (Vibrator Job)
- New  TBD   or separate   TBD    Manage status with table
- export results:
  - v1: Save local files/object storage after zip/json creation
- delete:
  - v1: Processing from instant deletable tables + log left
  - v2: Archive policy/inclusive(commerce)

### 4) Security / Audit
- You need to authenticate (token + additional confirmation options)
- All operations are recorded in   TBD  
- export file applied TTL/Men(e.g. 24h)

## Non-goals
- Compliance with GDPR/CCPA
- Deletion of commerce payments/tax data (who need to store them) — Anonymization/Policy on v2

## DoD
- export/delete request is executed in asynchronous and can be viewed in progress/status
- export output is accurate as user unit and no redundancy/no redundancy
- After delete, the main function data is actually removed (test validation)
- All requests/results in audit log

## Codex Prompt
Implement user data export/delete:
- Add endpoints via BFF and implement job-based processing using job_run (or privacy_job).
- Export user data to JSON/ZIP with TTL and secure download.
- Delete user data safely with idempotency, audit logging, and clear status transitions.
- Add integration tests verifying export content and delete effectiveness.
