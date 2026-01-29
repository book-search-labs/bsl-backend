# B-0273 — SR/RS Fallback Policy (Operational Safety): Keep SLA with Degrade when MIS Obstacles/Related

## Goal
MIS (model abstract) or RS (licensing) dependability**Release or disability**Release,
<# if ( data.meta.album ) { #>{{ data.meta.album }}<# } #> <# if ( data.meta.artist ) { #>{{ data.meta.artist }}<# } #>
SR /RS ** standardize Fallback/Degrade policy**

- MIS timeout/5xx → RS handles with “No spot”
- RS failure → SR** (1) Fusion order** or**(2) Return to BM25-only**
- Explanation to response whether or not quality( TBD  , reason)

## Background
- The biggest problem in operation **Scanning Obstacle**:
  - MIS slows → RS standby → SR standby → full search timeout
- SLA (providing response) is more than quality (precision).
- “Disable scenarios” must be designed as expressly.

## Scope
### 1) Budget & Timeout Standard (required)
- SR Full Budget Example (Environmental Adjustment):
  - BM25 retrieval: 80~150ms
  - Vector retrieval: 120~250ms (optional)
  - RS rerank call: 80~200ms
  - Total p99 target: 600~900ms (MVP)
- RS→MIS timeout:
  - timeout (e.g. 200ms)
  - connect timeout (example: 50ms)

### 2) Degrade phase (required)
**Stage A: Rerank degrade**
- Venue News
  - MIS timeout/5xx/queue reject(429/503)
- Venue News
  - RS returns rerank and “original candidate order” + degraded flag
  - SR responds as fusion result or bm25 results

**Stage B: Vector degrade**
- Venue News
  - embedding path failure / knn slow / OS partial failure
- Venue News
  - BM25-only

**Stage C: Total fail-safe**
- Venue News
  - OpenSearch Error/timeout, some shard failed
- Venue News
  - Return of "partial results" (if possible)
  - "friendly empty + retryable error meta" instead of empty results

### 3) Circuit Breaker / Hedging (Recommended)
- SR:
  - Application of circuit breaker to MIS/RS (constant time blocking when failure)
  - hedged request(optional): p99 Bounce prevention(Retention: Increased cost)
- RS:
  - Insulating MIS Calling Bulkhead

### 4) Response/Logging standard (required)
- SR Response   TBD   Field:
  - `pipeline.rerank_used` (bool)
  - `pipeline.vector_used` (bool)
  - `pipeline.degraded` (bool)
  - `pipeline.degrade_reason` (enum)
  - New  TBD   (by stage)
- Tag:
  - degrade rate
  - timeout rate
  - Mobile Site

## Non-goals
- Quality Optimization Self(=B-0266, B-0294 etc.)
- canary routing(=B-0274)

## DoD
- degrade policy on SR/RS is fixed in code/document
- In testing scenarios that cause MIS failure/painting:
  - SR retains 200/normal JSON response
  - New  TBD   and reason included
- metrics / dashboard indicators are exposed

## Degrade Reason Enum
- `MIS_TIMEOUT`
- `MIS_REJECTED`
- `MIS_5XX`
- `VECTOR_TIMEOUT`
- `OS_PARTIAL_FAILURE`
- `RS_TIMEOUT`
- `UNKNOWN`

## Codex Prompt
Implement SR/RS degrade policy:
- Add strict timeouts and circuit breakers for RS→MIS and SR→RS.
- If MIS fails, return non-reranked results with pipeline.degraded flags.
- If vector/hybrid fails, fallback to BM25-only.
- Add metrics for degrade reasons and timeout rates, and include pipeline metadata in responses.
