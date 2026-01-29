# I-0318 — Add Offline Eval Gate to CI (Prohibition Drop Distribution)

## Goal
If you enter search/langing/model change, return Offline Eval automatically from CI
New *If the performance drops are compared to the standard, we block the merge/distribution.

## Why
- “The search will be well” is always broken (e.g. index/ul/model/replacement)
- The core of the operating portfolio is the “Quality Anti-Return” device

## Scope
### 1) Eval running mode
- Fixed in the CLI command form:
  - New  TBD   or   TBD  
- Type News
  - golden/shadow/hard query set
  - baseline snapshot (previous model/policy results) or stored standard metrics
- Output:
  - New  TBD   + Summary Table
  - Failure Ownership (how much indicator has fallen)

### 2) CI workflow
- In PR:
  - Light: Golden(Sample) Only
- In main/tag:
  - shadow subset
- Failure Condition (e.g.):
  - NDCG@10 -0.5%p or less
  - 0-result-rate +0.2%p or higher
  - Recall
  - latency proxy upper limit

### 3) Save Results
- model registry/eval run
- CI artifact

## Non-goals
- Full Automatic Tuning/Choose Optimal Model(add)

## DoD
- eval is automatically executed in PR, and the CI fails
- Failure reports are left to “the level you can figure out”
- Validation of the minimum 1 real regression situation

## Codex Prompt
Add offline-eval regression gate to CI:
- Provide eval runner CLI producing eval_report.json and pass/fail based on thresholds.
- Integrate into GitHub Actions for PR and main pipelines.
- Upload reports as artifacts and print a concise summary in CI logs.
