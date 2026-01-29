# B-0221b — Authority/Merge v1 (material/agent dedup minimal set)

## Goal
The NLK-based canonical data is organized by the “minimum level of operation”**.
- New *Material(Document) Duplicate Bundle**: Grouping edition/recovery/set/recovery record candidate
- New *Agent(Lower) Notation String Stringing**: Mapping with the same character canonical
- Search results Duplicate Exposure + CTR/Pitch Dispersion Prevention (=LTR Success Based)

## Background
- LOD/Large capacity ingest is duplicate, and if the duplicate remains:
  - SERP is a “like book” -> UX/CTR worsening
  - Click/Buy logs are distributed → Edit(ctr smooth/popularity) distortion
  - LTR Label/Finished Quality

## Scope (v1: minimal & deterministic)
### 1) Produced Material merge candidate (batch)
- Candidate Rules (Secretary):
  - (A) ISBN Same OR
  - (B)   TBD   proximity + similarity (simple token Jaccard/Levenshtein) standard
  - (C) series + volume same
- Results:   TBD  on group creation (OPEN status)

### 2) Master(CEO) Selection Rule(v1)
- Basic rules:
  - ISBN-13 exists > ISBN-10 exists > issued year Latest > Meta field rich (title/subtitle/author/publisher/summary)
- master id to group

### 3 years Agent alias
- Notes:
  - name norm
  - One person/Hangle bottle (pre-based if possible)
  - Yeon Woo-jin Park Eun-bin Double-Edge spectator points
- Results:   TBD   creation(OPEN)

### 4) “Applicable” separated (maintenance)
- New *V1 does not reflect auto merge directly to canonical**
  - (a) Candidate creation + automatic until master selection
  - (b) Approval of operation (A-0130) after reflecting (or unapproved, “search grouping only” priority)
- The reflecting method extends from B-0300/B-0301(simplified)

## Non-goals
- Fully automatic canonical rewrite(deep)
- Adjustment of disambiguation, the name of the verb
- ML-based entity resolution

## Data Model (suggested)
- material_merge_group(group_id, status, master_material_id, members_json, rule_version, created_at)
- agent_alias_candidate(candidate_id, status, canonical_agent_id, variants_json, rule_version, created_at)
- agent alias(canonical agent id, alias text, source, created at) — Fixed table after approval

## Interfaces / Jobs
- `job_type=AUTHORITY_CANDIDATE_BUILD`
- params:
  - since date
  - rule_version
- outputs:
  - new groups, counts, sample preview

## Observability
- metrics:
  - authority_material_groups_created
  - authority_agent_candidates_created
  - approval rate (after admin approval)
- logs:
  - rule_version, thresholds, sample pairs

## DoD
- idempotent can be redisposable for the day-to-day test
- Candidate Group/alias Candidates Stack to DB and Check Sampling
- Master Selection Rule Documentation + Reproduction
- (Optional) can be used in group id-based “recovery grouping” in search

## Codex Prompt
Implement minimal deterministic authority/merge v1:
1) batch job to build material merge candidates + choose master
2) batch job to build agent alias candidates
   Persist results in tables with rule_version, idempotency, and metrics/logging.
   Do not automatically rewrite canonical; keep it approval-driven.
