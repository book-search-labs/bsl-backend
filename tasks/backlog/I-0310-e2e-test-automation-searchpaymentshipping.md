# I-0310 — E2E Test Automation (Search → Purchase → Order → Payment → Shipping)

## Goal
Automatically validate the core user flow with **E2E**
We use cookies to ensure that we give you the best experience on our website.

## Why
- In microservice/front separation, the function is often broken from “integrated”
- Only contract testing (B-0226) does not fail UI/Floor

## Scope
### 1) Test Level
- API E2E: Running scenarios based on BFF
- UI E2E (optional): Web User/Admin core screen only with Playwright

### 2) Required scenario (v1)
Search:
- Search → Check results → Enter details

Autocomplete:
- <# if ( data.meta.album ) { #>{{ data.meta.album }}<# } #>

Commerce:
- {$*display product new icon} {$*display product recommand icon} {$*display product stock icon}

Ops:
- reindex job trigger → job status check

### 3) Test data/fixed seeds
- Test-only user/product/document seeds
- idempotent reset

### 4) CI Integration
- Launch API E2E in PR/merge
- Run UI E2E with nightly(optional)

## Non-goals
- Full coverage of all cases (only "Core flow")

## DoD
- E2E test suite can be automatically executed (local + CI)
- Provides log/screenshot (optional) which is broken at any stage when failure
- Test Data Seed/reset Procedure Documentation
- Min. 1 Release Gate (merge blocking)

## Codex Prompt
Implement E2E automation:
- Add API-level E2E tests against BFF for search/autocomplete/detail (and commerce later).
- Optionally add Playwright smoke UI tests for web-user/admin.
- Ensure deterministic test data seeding and cleanup.
- Integrate with CI so failures block merges.
