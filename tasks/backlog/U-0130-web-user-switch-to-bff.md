# U-0130 — Web User: Convert API calls to BFF (BFF primary + direct fallback)

## Goal
Currently, QS/Other APIs that Web User has been called directly to the BFF Single Entry Point**.
- Step 1: BFF Priority Call + Direct fallback Toggle**
- Step 2: Remove direct-call after stabilization

## Why
- You need to control the operating standard (certification/rate-limit/observation/Event) from BFF
- The front is vulnerable to “API changes” → needs to be performed on the toggles

## Scope
### 1) Add API routing layer
-  TBD  adding routing logic to:
  - env: `VITE_API_MODE=bff_primary|direct_primary|bff_only`
  - fallback(network error/5xx center, 4xx ban fallback)

### 2) Target endpoint conversion
- Search: `/search`
- Autocomplete: `/autocomplete`
- Book detail: `/books/:id`
- Chat:   TBD   (Phase 7, but the interface is pre-connected)

### 3) Common header/tracking
- New  TBD  (according to client creation or BFF creation policy)
-  TBD  
- include request id in error log

### 4) Observation/Release check
- BFF route vs direct route rate logging (front side)
- Error rate/latency comparison (with shorter indicator)

## Non-goals
- Authentication/Registration Self Implementation (B-0227 is responsible for BFF)

## DoD
- Can work with   TBD   in prod
- direct fallback works normal in real obstacle situation
-  TBD  

## Interfaces
- BFF base: `VITE_BFF_BASE_URL`
- Direct base:   TBD 

## Files (example)
- New  TBD   (Routing/Relay/Error Classification)
- `web-user/src/api/search.ts`
- `web-user/src/api/autocomplete.ts`
- `web-user/src/api/books.ts`
- `web-user/src/api/chat.ts`

## Codex Prompt
Migrate Web User API calls to BFF with zero downtime:
- Add API routing with env toggles and safe fallback logic.
- Switch search/autocomplete/book detail/chat calls to go through the router.
- Add request_id propagation and lightweight telemetry logs.
