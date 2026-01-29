# I-0309 — Load/Performance Test (Search p99 + Indexing throughput)

## Goal
For serving / indexing routes, we will build a reactive load test**,
Measures/Records**p95/p99, error rate, throughput**.

## Why
- “Slow/Timeout/cost” is the most frequently used operation
- Hybrid(kNN), rerank(MIS), QS 2-pass is easy to be bottled

## Scope
### 1) Scenario (min. v1)
Serving:
- /search (BM25-only)
- /search (hybrid + RRF + rerank)
- /autocomplete (redis hit / miss)
- /books/:id

Indexing:
- reindex job(books_doc) throughput
- ac candidates update viaput

### 2) Tools
- k6 or Locust (recommended: k6)
- Tag:
  - hot queries(top 1k)
  - long-tail queries(Random 5k)
  - hard queries(Ota/Secret/Charger)

### 3) Measurement indicator
- latency: p50/p95/p99
- error rate: 4xx/5xx/timeout
- dependency latency: OS/MIS/QS step by step
- Cost proxy:
  - QS 2-pass Call Rate
  - MIS call rate (topR)
  - embedding call rate (including cache hit)

### 4) Report/gate (optional)
-  TBD   
- Set the minimum smoke load before release (optional)

## Non-goals
- A complete capacity plan in a large distributed environment (out of the initial range)

## DoD
- k6/locust scripts are included and recreated
- Run 10~30 minutes test on local/staking
- Results reports (marks / graphs) + bottleneck analysis notes included
- “Current SLO standard” documenting (p99 goals, etc.)

## Codex Prompt
Add performance/load testing:
- Implement k6 (or Locust) scenarios for search/autocomplete/detail and indexing jobs.
- Collect latency percentiles, error rates, and dependency stage metrics.
- Produce a reproducible report output and document how to run it in stage.
