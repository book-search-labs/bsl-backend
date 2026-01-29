# B-0224 — Synonym/Normalization Deployment Pipeline (versioning + rollback)

## Goal
We use cookies to ensure that we give you the best experience on our website. If you continue to use this site we will assume that you are happy with it.Ok
- Manage synonym set to DB version
- OpenSearch analyzer reflection
- Available for rollback
- reindex

## Background
- The synonyms/consultation changes more often than “code distribution”, and if they are wrong, the search will be broken.
- So version/rollback/delete required

## Scope
### 1) Synonym Set Storage
- synonym_set(set_id, name, version, content_text, status, created_at)
- status:
  - DRAFT / ACTIVE / DEPRECATED
- 1 active version (or alias)

### 2) Deployment Job
- steps:
  1) validate syntax (recovery/rupe/gold)
  2) upload to OpenSearch (synonyms API or file-based depending on setup)
  3) apply analyzer reload (reload, or reindex required)
  4) Smoke query check(Sample query)
- ACTIVE

### 3) Rollback
- ACTIVE version pointer
- LOGISTICS reload orindex re

### 4) Admin/Ops integration
- A-0107(Policy UI) or A-0113(ops)
  - Distribution/rollback trigger possible (required)

## Non-goals
- Create synonyms automatically with full meaning
- Multi-language synonym Advanced (Extra)

## Observability
- deploy status, duration, validation failures
- audit log: Who has activated any version

## DoD
- Create synonym version → validate → deploy → active conversion
- Transfer version instantly recoverable with rollback button / command
- Failure to deploy fail fails to affect the search service fail-safe

## Codex Prompt
Implement synonym/normalization deployment pipeline:
DB versioned synonym_set, validation, OpenSearch apply/reload, and rollback.
Ensure fail-safe behavior (keep previous ACTIVE on failure) with audit logs and metrics.
