# T-0211 — Local OpenSearch v1.1: add ac_suggest + authors/series + aliases + seed

## Goal
Extend the existing **Local OpenSearch v1.1** bootstrap (built in T-0210) to include the remaining **final index set** for MVP UI features:

- `ac_suggest_v1_*` (unified autocomplete candidates)
- `authors_doc_v1_*` (author entity index)
- `series_doc_v1_*` (series entity index)

After this ticket, a developer should be able to run **one command** to:
1) start OpenSearch via Docker  
2) create **doc/vec/ac/authors/series** indices (versioned)  
3) wire **read/write aliases** (blue/green style)  
4) seed **minimal deterministic sample docs** for each index  
5) run smoke checks for:
   - autocomplete prefix search
   - author lookup search
   - series lookup search
   - (and keep the existing doc/vec smoke checks)

Non-goals:
- No services/** changes
- No contracts/** changes
- No DB changes

---

## Must Read (SSOT)
- `AGENTS.md`
- `infra/opensearch/INDEX_VERSIONING.md` (if present)
- `docs/INDEXING.md` or `docs/ARCHITECTURE.md` (if present)
- Existing scripts from T-0210:
  - `scripts/os_bootstrap_indices_v1_1.sh` (or equivalent)
  - `scripts/os_seed_books_v1_1.sh` (or equivalent)

---

## Scope

### Allowed
- `infra/**`
- `scripts/**`
- `docs/RUNBOOK.md` (create/update if missing)

### Forbidden
- `services/**`
- `contracts/**`
- `db/**`

---

## Environment Assumptions
- macOS/Linux (bash)
- Docker + Docker Compose
- Default OpenSearch HTTP port: `9200`
- Security disabled for local dev (no auth)

---

## Implementation Requirements

### 1) Add mapping files for new indices

#### A) `infra/opensearch/ac_suggest_v1.mapping.json`
Based on the final design (edge-ngram prefix). Minimum required fields:

- `suggest_id` keyword
- `type` keyword  (QUERY | TITLE | AUTHOR | SERIES)
- `lang` keyword
- `text` text (`ac_index`/`ac_search`)
- `text_kw` keyword (normalizer `kw_norm`)
- `target_id` keyword
- `target_doc_id` keyword
- `payload` object enabled:false
- `weight` integer
- `popularity_7d` float
- `ctr_7d` float
- `last_seen_at` date
- `updated_at` date

**Settings**
- analyzer `ac_index`: standard + lowercase + asciifolding + edge_ngram
- analyzer `ac_search`: standard + lowercase + asciifolding
- normalizer `kw_norm`: lowercase + asciifolding
- `dynamic: strict`

✅ Done:
- `curl -XPUT ...` with the mapping file succeeds without errors.

---

#### B) `infra/opensearch/authors_doc_v1.mapping.json`
Minimum required fields:

- `author_id` keyword
- `name_ko` text (nori-based analyzer) + `.raw` keyword
- `name_en` text (optional)
- `bio` text (optional)
- `work_count` integer
- `top_doc_ids` keyword
- `rank.popularity_30d` rank_feature (optional but recommended)
- `updated_at` date

**Settings**
- analyzer `ko`: nori_tokenizer + lowercase + asciifolding
- normalizer `kw_norm`: lowercase + asciifolding
- `dynamic: strict`

✅ Done:
- `curl -XPUT ...` with the mapping file succeeds without errors.

---

#### C) `infra/opensearch/series_doc_v1.mapping.json`
Minimum required fields:

- `series_id` keyword
- `name` keyword (or text + keyword, but keep minimal)
- `work_count` integer
- `top_doc_ids` keyword
- `updated_at` date

**Settings**
- keep minimal (`dynamic: strict`)

✅ Done:
- `curl -XPUT ...` with the mapping file succeeds without errors.

---

### 2) Extend index bootstrap to include new indices + aliases

Update the existing bootstrap script (preferred) OR add a new one:

- Preferred: extend `scripts/os_bootstrap_indices_v1_1.sh`
- Alternative: create `scripts/os_bootstrap_indices_v1_1_extras.sh`

**Responsibilities**
- bash, `set -euo pipefail`
- env defaults:
  - `OS_URL=http://localhost:9200`
  - `AC_INDEX=ac_suggest_v1_20260116_001`
  - `AUTHORS_INDEX=authors_doc_v1_20260116_001`
  - `SERIES_INDEX=series_doc_v1_20260116_001`
- create indices using mapping files:
  - `infra/opensearch/ac_suggest_v1.mapping.json`
  - `infra/opensearch/authors_doc_v1.mapping.json`
  - `infra/opensearch/series_doc_v1.mapping.json`
- if indices exist:
  - default: delete and recreate (local dev)
  - `KEEP_INDEX=1` → do not delete
- attach aliases:
  - `ac_suggest_read` → AC_INDEX
  - `ac_suggest_write` → AC_INDEX (is_write_index=true)
  - `authors_doc_read` → AUTHORS_INDEX
  - `authors_doc_write` → AUTHORS_INDEX (is_write_index=true)
  - `series_doc_read` → SERIES_INDEX
  - `series_doc_write` → SERIES_INDEX (is_write_index=true)

✅ Done:
- `_cat/aliases?v` shows the new aliases + existing doc/vec aliases.

---

### 3) Seed minimal deterministic docs for new indices

Update the existing seed script (preferred) OR add a new one:

- Preferred: extend `scripts/os_seed_books_v1_1.sh`
- Alternative: create `scripts/os_seed_entities_v1_1.sh`

**Responsibilities**
- bash, `set -euo pipefail`
- env defaults:
  - `OS_URL=http://localhost:9200`
  - `AC_ALIAS=ac_suggest_write`
  - `AUTHORS_ALIAS=authors_doc_write`
  - `SERIES_ALIAS=series_doc_write`
- bulk insert NDJSON (must end with newline):
  - `ac_suggest`: at least 6 docs total including:
    - 2 QUERY suggestions (e.g., "해리포터", "클린 코드")
    - 2 TITLE suggestions mapped to `target_doc_id` (e.g., b1, b3)
    - 1 AUTHOR suggestion mapped to `target_id` (e.g., a1)
    - 1 SERIES suggestion mapped to `target_id` (e.g., s1)
  - `authors_doc`: at least 2 authors:
    - `author_id=a1`, `name_ko="J.K. 롤링"` with `top_doc_ids=["b1","b2"]`
    - `author_id=a2`, `name_ko="로버트 C. 마틴"` with `top_doc_ids=["b3"]`
  - `series_doc`: at least 1 series:
    - `series_id=s1`, `name="해리 포터"`, `top_doc_ids=["b1","b2"]`
- refresh all indices after bulk insert.

**Smoke checks**
1) Autocomplete prefix (text starts with "해"):
   - `POST /ac_suggest_read/_search` using match on `text` or prefix-like query
   - must return hits >= 1
2) Author lookup:
   - `POST /authors_doc_read/_search` match on `name_ko` for "롤링"
   - must return hits >= 1
3) Series lookup:
   - `POST /series_doc_read/_search` term/match on `name` for "해리"
   - must return hits >= 1

✅ Done:
- All three smoke checks pass and print a clear “OK” summary.
- Existing doc/vec smoke checks still pass.

---

### 4) One-command local up/down stays the same
Ensure `scripts/local_up.sh` still runs end-to-end and now includes bootstrapping + seeding for the new indices
(either via updated scripts or additional script calls).

✅ Done:
- `chmod +x scripts/*.sh && ./scripts/local_up.sh` succeeds
- `curl -s http://localhost:9200/_cat/aliases?v` includes all aliases
- smoke checks all pass

---

### 5) RUNBOOK update
Update `docs/RUNBOOK.md` to include a short “Local OpenSearch v1.1 (Full Set)” section (<= 12 lines):

Must include:
- Start: `./scripts/local_up.sh`
- Check cluster: `curl http://localhost:9200`
- Check aliases: `curl -s http://localhost:9200/_cat/aliases?v`
- Autocomplete smoke query on `ac_suggest_read`
- Author smoke query on `authors_doc_read`
- Series smoke query on `series_doc_read`
- Stop: `./scripts/local_down.sh`

---

## Acceptance Tests (What to run)
1) `chmod +x scripts/*.sh`
2) `./scripts/local_down.sh`
3) `./scripts/local_up.sh`
4) `curl -s http://localhost:9200/_cat/aliases?v`
5) Autocomplete smoke returns hits >= 1
6) Author smoke returns hits >= 1
7) Series smoke returns hits >= 1
8) `./scripts/local_down.sh`

---

## Output (in local summary)
- List created/updated files
- Copy-paste run commands
- Any known issues (ports, Docker memory)
