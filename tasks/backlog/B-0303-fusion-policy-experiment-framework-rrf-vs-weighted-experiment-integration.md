# B-0303 — Fusion Policy Experimental Frame (RRF vs Weighted) + Experimental Connection

## Goal
"Fusion(RRF/Weighted/ rule-based)"
New *Experiment/FeatureFlag** to share your traffic with us **Online/Offline evaluation**

## Why
- RRF is good at default, but depending on domain/traffic, Weighted(intermediate) or rule-based may be better.
- Fusion is a great impact on the quality, and if it changes to the distribution, it is slow and dangerous → need a experimental frame

## Scope
### 1) Fusion Strategy interface/plugin structure (SR internal)
- `FusionStrategy`:
  - input: `bm25_ranked_docs`, `vector_ranked_docs` (+ optional scores)
  - output: `fused_ranked_docs` + debug breakdown
- Features:
  - `RrfFusionStrategy`
  - New  TBD   (including weights, score norm policy)
  - New  TBD   (ex: ISBN/Accurate)

### 2) Fusion Config (Policy/Label Value)
- New  TBD  (or   TBD  ) in the table:
  - `fusion_mode` (RRF/WEIGHTED/RULE)
  - `fusion_params_json` (rrf_k, weights, score_norm, caps)
- BFF's policy or query in SR(the following 1)

### 3 years ) Experiment Link
- Determining experiment bucket as request unit:
  - `exp_fusion_mode`: control(RRF) vs variant(WEIGHTED)
- Includes experiment information on event logging (B-0232)

### 4) Evaluation Integration
- From Offline eval(B-0295) to **pipeline config** to compare fusion strategy scores
- config to map   TBD    and

## Non-goals
- Build a complete experimental platform (can start with a bucket hash base)
- Automated multi-variable optimization (add)

## DoD
- Switchable to fusion strategy in SR to config
- debug=true when fusion breakdown is exposed (Rank/Point/Width)
- Compared to the same query set to fusion by offline eval
- search impression events include experiment/policy

## Codex Prompt
Implement fusion experiment framework:
- Create FusionStrategy interface and implement RRF and Weighted fusion with configurable params.
- Add policy/experiment config fields for fusion_mode and params.
- Include fusion breakdown in debug responses and persist experiment identifiers in search events.
- Ensure offline eval runner can run multiple fusion configs and compare results.
