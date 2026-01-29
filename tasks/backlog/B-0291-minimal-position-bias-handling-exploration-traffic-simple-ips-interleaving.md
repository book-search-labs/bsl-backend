# B-0291 — Position Bias Minimum response: 1 navigation traffic/simultaneous IPS/interior ice(+fresh)

## Goal
In the Implicit feedback-based LTR learning, the**position bias (horizontal exposure defragment)** is minimal.
If the MVP is not a “correction”, it makes a safety device that blocks the level of learning.

## Background
- Click "Related" + "Export ranking" is a signal that is mixed, and it will generate a self-expansion that will only be enhanced.
- Propensity/Interleaving/Randomization

## Options (Home 1, Referral Priority)
### Option A: **Exploration bucket(Random shuffle/part random)* News
- 1~5% of total traffic   TBD  
- Some sections of the TopN candidates (e.g. 5–20) are exposed by the random shuffle**
- Only the logs of the bucket are used for labeling weight/learning

### Option B: **Propensity correction**
- Predict propensity p(pos) by position(first term heuristic or log-based)
- Weight = 1 / p(pos) given to the learning sample(clipping required)

### Option C: **Team Draft Interleaving (A/B comparison)* News
- Existing ranker vs new ranker results
- Convert Click to Win (Power to Online Comparison)
- (MVP is costly → cold)

## Scope (v1 Recommended: Option A + Simple Logging)
1) **Experiment routing**
- Allocation bucket from SR or BFF:
  - `control` / `explore`
- search impression event   TBD  ,   TBD   included

2) New *Explore Exposure Policy**
- TopN:
  - Top 1~4 fixed
  - 5 to 20 sections random shuffle (or 5 to 10 only shuffle)
- DoS/Quality Low-Proof:
  - “Exclusive (ISBN/Perfect)” query except Explore

3) New *Offline label/learning**
- New  TBD   When label creation +   TBD   Columbia Conservation
- Learning Dataset:
  - Explore bucket priority use (or weight ↑)

4) Guardrails
- Explore Traffic Rate (Basic 1%)
- KPI monitoring (automatic off when CTR is fast)

## Non-goals
- Sophisticated propensity modeling (Advanced IPS)
- Full interleaving system

## DoD
- Explore bucket is actually created and left on the log
- SERP applied to explore exposure is provided to users (1% level)
- Deleting explore/control from label creation results to statistical verification
- Explore off Toggles (Environment/feature flag)

## Codex Prompt
Implement minimal position-bias mitigation:
- Add experiment buckets (control/explore) to search requests and events.
- For explore bucket, randomize a safe slice of ranks (e.g., positions 5-20) with guardrails (exclude ISBN/exact-match queries).
- Ensure events carry experiment_bucket and can be used by label generation (B-0290).
- Add toggle to disable exploration instantly.
