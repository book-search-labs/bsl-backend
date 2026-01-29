# B-0295 — Offline Eval Runner + Regression Gate (Distribution)

## Goal
The search/langing pipeline (ritribal→furbish→rirank/LTR) is changed, but the quality lower is detected in CI and prevent distribution.

## Why
- Index mapping/shinon/quarie DSL/mid/model version change easily break quality
- “Being broken on online” blocking costs from CI

## Scope
### 1) Set of Eval Dataset (min. 3 types)
- New *Golden Set**: Fixed (e.g. 300~2000 queries) — Regression checks (Long term stable)
- New *Shadow Set**: Latest Popular/Hot Quarry (Yes: 5k) — Trend/Drift Detection
- New *Hard Set**: Otta/Ultrasonic/Character/Series/0 candidates — QS/SR sensing quality

> Storage Mode:   TBD  (DB) +   TBD  (query, expected doc ids optional)

### Runner
- Type News
  - New <# if ( data.meta.album ) { #>{{ data.meta.album }}<# } #>
  - New  TBD  : model registry active or specified version
- Open News
  - Query set   TBD  Call(Recommended: SR direct)
  - Results/Score/latency/probe stores logs

### 3 years ) Metrics (Required)
- **NDCG@10**
- **MRR@10**
- New *Recall@100**
- **0-result-rate**
- New *Latency proxy**(p95/p99 per stage, rerank call rate)

> Without qrels:
- Golden set starts with a person label (small quantity) or “known-good doc id” method
- Shadow/Hard gates around coverage/latency/zero-rate

### 4) Regression Gate
- NDCG@10: Preparing baseline**-0.5%p and below**
- 0-result -rate: Compared to baseline **+0.2%p or more**
- Recall@100: Preparing baseline** Large drop (e.g. -1%p)** If FAIL
- p99 latency: FAIL if the budget exceeds the threshold

baseline   TBD 

### 5) Result Storage/Reporting
- New  TBD   in table:
  - metrics_json, config_json, model_version, index_alias, git_sha, created_at
- Delivery Time:
  - markdown summary + json artifact
- Failure Case Extract:
  - Save as "TopK"   TBD  (Optional)

## Non-goals
- Fully automatic labeling (first-time manual/correction based on doc id)
- Online A/B Final Decision (Don't Experimental System)

## DoD
- eval runner is running with   TBD   (or script) in local
- return PASS/FAIL to compare baseline(Process exit code)
- eval run is stored in DB and reports are generated
- Failure scenarios are actually caught based on minimum Golden/Hard set

## Interfaces / Contracts
- Minimum in SR debug response:
  - request_id, items(doc_id, rank_score, stage scores), pipeline(meta), timings(stage_ms)
- Runner CLI:
  - `python -m eval.run --set GOLDEN --pipeline rrf_ltr_ce --model ltr_v1`

## Codex Prompt
Implement offline eval runner + regression gate:
- Define eval query sets (golden/shadow/hard) and storage format.
- Run SR searches with debug enabled, compute NDCG/MRR/Recall/zero-rate/latency metrics.
- Compare against a baseline run and fail with exit code when thresholds breach.
- Persist eval_run with metrics/config/model/index/git info and generate a markdown report.
