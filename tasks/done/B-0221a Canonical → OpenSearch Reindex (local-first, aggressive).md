# B-0221a Canonical → OpenSearch Reindex (local-first, aggressive)

## Goal
- Rebuild the OpenSearch `books_doc` index end-to-end from the Canonical MySQL database: **drop → redesign → create → bulk load**.
- Since this is **local development only**, it’s okay to be aggressive and freely change **mappings/analyzers/templates**.
- Ensure the rebuilt index supports basic search flows (e.g., core search and basic detail retrieval).

## Context
- The Canonical schema is defined in `./db/migration/V3__catalog_core.sql`.  
  → Treat this file as the **source of truth** for tables/relations and for designing joins/denormalization.
- Assume Raw → Canonical loading has already been completed.

## Scope
### In
1) Redefine the search index schema from Canonical
- Design a document model for search based on Canonical (material-centric + relation tables).
- Define and create the OpenSearch index (and/or index template) accordingly.
- In local dev, it is allowed to delete existing indices/templates and recreate them.

2) Implement the reindex pipeline
- Read from Canonical (material-centric + required joins) and denormalize into search documents.
- Bulk index into OpenSearch (include batching, retries, and failure logging).
- Provide an easy local entrypoint (script/command/Makefile target).

3) Basic verification
- Check indexed document count.
- Run a few sample search queries to confirm hits.
- Ensure failures are diagnosable via logs.

### Out
- Production-grade blue/green + alias swap + rollback (later)
- Idempotent/incremental upsert (later: B-0222)
- Observability/Ops UI (later)

## Inputs (must use)
- Canonical DDL: `./db/migration/V3__catalog_core.sql`
- Interpret Canonical entities/relations (e.g., `material`, `agent`, `concept`, `material_agent`, `material_concept`, `material_identifier`, etc.) based on that DDL.

## Design Freedom (local-only)
- No need to preserve compatibility with any existing OpenSearch mapping.
- Free to change field structure/types (including nested vs object), analyzers, templates, and index naming.
- Allowed to `DELETE` indices/templates and recreate them as needed.

## Tasks
- [ ] Read `V3__catalog_core.sql` and design a material-centric join/selection strategy
- [ ] Draft the search document schema (fields/types/analyzers) suitable for basic search
- [ ] Implement index/template creation (JSON or code)
- [ ] Implement canonical → document transform + bulk indexer (streaming/batching)
- [ ] Provide a local entrypoint:
  - e.g., `make reindex-books` or `./scripts/reindex_books.sh`
- [ ] Add minimal verification steps (count + a few sample queries)

## Acceptance Criteria (DoD)
- [ ] A single local command can run: “drop → create → bulk load”
- [ ] A meaningful number of documents is indexed and basic search works
- [ ] When failures occur, the root cause (mapping/analyzer/data issues) is traceable via logs

## Deliverables
- Index creation definitions (template/mapping/settings JSON or code)
- Bulk indexer implementation
- Run script / Makefile target
- Minimal verification script or checklist

## How to Test (local)
1) Start MySQL/OpenSearch (e.g., docker compose)
2) Run `make reindex-books` (or the provided script)
3) Verify `_count` in OpenSearch
4) Run a few sample search calls and confirm results
