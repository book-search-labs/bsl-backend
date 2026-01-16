# T-0210 — Local OpenSearch v1.1: doc/vec indices + aliases + seed

## Goal
Upgrade the local OpenSearch runtime to match the **final dual-index design (doc/vec split)** and make it reproducible with scripts.

After this ticket, a developer should be able to run **one command** to:
- start OpenSearch via Docker
- create the following indices (versioned)
  - `books_doc_v1_*`
  - `books_vec_v1_*`
- attach aliases (blue/green)
  - `books_doc_read`, `books_doc_write`
  - `books_vec_read`, `books_vec_write`
- bulk seed **5 sample books** into both doc+vec indices (same `doc_id`)
- run smoke checks:
  - lexical search on `books_doc_read` returns >= 1 hit for “해리”
  - kNN search on `books_vec_read` returns >= 1 hit using a deterministic query vector

Non-goals:
- No services/** changes
- No contracts/** changes
- No DB changes

---

## Must Read (SSOT)
- `AGENTS.md`
- `infra/opensearch/INDEX_VERSIONING.md` (if present)
- This design note (doc/vec split, aliases):
  - `docs/INDEXING.md` (if present) or `docs/ARCHITECTURE.md`

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
- Default OpenSearch HTTP port: `9200` (print friendly error if unavailable)
- Security disabled for local dev (no auth)

---

## Implementation Requirements

### 1) Docker runtime
Update or create:
- `infra/docker/docker-compose.yml`

Requirements:
- single-node OpenSearch
- container name: `opensearch`
- ports:
  - `9200:9200` (HTTP)
  - `9600:9600` (performance analyzer)
- env:
  - `discovery.type=single-node`
  - `plugins.security.disabled=true`
  - `OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m`
- add a healthcheck that polls:
  - `GET http://localhost:9200/_cluster/health`

✅ Done:
- `docker compose -f infra/docker/docker-compose.yml up -d`
- `curl http://localhost:9200` returns cluster info

---

### 2) OpenSearch mappings (doc/vec)
Create the following mapping files (or update existing ones):

#### A) `infra/opensearch/books_doc_v1.mapping.json`
Based on the latest design:
- index settings: analysis (ko/en analyzers, keyword normalizer)
- mappings:
  - `doc_id` keyword
  - `title_ko` text (ko_index/ko_search) + `.raw` keyword + `.edge` (edge analyzer)
  - `title_en` text (en_index/en_search) + `.raw` keyword
  - `authors` as **nested** with:
    - `agent_id` keyword
    - `name_ko` text + `.raw` keyword
    - `name_en` text
    - `role` keyword, `ord` short
  - `publisher_name` keyword
  - `identifiers.isbn13` keyword
  - `language_code` keyword
  - `issued_year` short
  - `volume` short
  - `edition_labels` keyword
  - `category_paths` keyword
  - `concept_ids` keyword
  - `is_hidden` boolean (default false in data)
  - `redirect_to` keyword (optional)
  - `updated_at` date

Notes:
- Keep `dynamic: strict`
- Keep field count reasonable
- This mapping should be **put-able** as-is.

#### B) `infra/opensearch/books_vec_v1.mapping.json`
Based on the latest design:
- settings:
  - `index.knn: true`
- mappings:
  - `doc_id` keyword
  - `language_code` keyword (optional filter)
  - `category_paths` keyword (optional filter)
  - `concept_ids` keyword (optional filter)
  - `embedding` knn_vector
    - dimension: `1024` (fixed for this ticket)
    - HNSW lucene, cosine similarity
  - `updated_at` date
- Keep `dynamic: strict`

✅ Done:
- `curl -XPUT ...` with those mapping files succeeds (no mapping errors)

---

### 3) Index creation + alias wiring
Create a script:
- `scripts/os_bootstrap_indices_v1_1.sh`

Responsibilities:
- bash, `set -euo pipefail`
- configurable via env:
  - `OS_URL` default `http://localhost:9200`
  - `DOC_INDEX` default `books_doc_v1_20260116_001`
  - `VEC_INDEX` default `books_vec_v1_20260116_001`
- create indices using mapping files:
  - `infra/opensearch/books_doc_v1.mapping.json`
  - `infra/opensearch/books_vec_v1.mapping.json`
- if indices exist:
  - default: delete and recreate (local dev)
  - if `KEEP_INDEX=1`, do not delete
- attach aliases (blue/green):
  - `books_doc_read` → DOC_INDEX
  - `books_doc_write` → DOC_INDEX (is_write_index=true)
  - `books_vec_read` → VEC_INDEX
  - `books_vec_write` → VEC_INDEX (is_write_index=true)

✅ Done:
- Running the script results in indices + aliases present:
  - `_cat/aliases?v` shows all four aliases

---

### 4) Seed sample docs (doc + vec) deterministically
Create a script:
- `scripts/os_seed_books_v1_1.sh`

Responsibilities:
- bash, `set -euo pipefail`
- env:
  - `OS_URL` default `http://localhost:9200`
  - `DOC_ALIAS` default `books_doc_write`
  - `VEC_ALIAS` default `books_vec_write`
- Insert **5 sample books** into doc index (bulk NDJSON, terminated with newline).
  - include at least these fields:
    - `doc_id`
    - `title_ko`
    - `authors` (nested objects)
    - `publisher_name`
    - `language_code` = "ko"
    - `issued_year`
    - `volume` (at least one doc with volume=1)
    - `edition_labels` (include one doc with ["recover"])
    - `identifiers.isbn13` (fake ok)
    - `category_paths` (fake ok)
    - `concept_ids` (fake ok)
    - `is_hidden` = false
    - `updated_at`
- Insert matching 5 docs into vec index (bulk NDJSON).
  - Same `doc_id` values as doc index
  - Provide deterministic `embedding` vectors of dimension 1024.
    - Use a simple deterministic generator in bash+python:
      - `python - <<'PY' ...` to print a JSON array of 1024 floats
      - Use a fixed seed per doc_id so results are stable (e.g. hash(doc_id))
- Refresh both indices.
- Smoke checks:
  1) Lexical:
     - `POST /books_doc_read/_search` with match on `title_ko` for “해리”
     - must return hits >= 1
  2) Vector:
     - `POST /books_vec_read/_search` with `knn` query against `embedding`
     - use the same deterministic query vector as one of the seeded docs
     - must return hits >= 1

✅ Done:
- Both smoke checks pass and print a clear “OK” summary.

---

### 5) One-command local up/down
Update/create scripts:

#### `scripts/local_up.sh`
Responsibilities:
- `docker compose -f infra/docker/docker-compose.yml up -d`
- wait up to 60s for OpenSearch to be ready
- run:
  - `scripts/os_bootstrap_indices_v1_1.sh`
  - `scripts/os_seed_books_v1_1.sh`

On failure:
- print last 200 lines of OpenSearch logs and exit non-zero

#### `scripts/local_down.sh`
Responsibilities:
- `docker compose -f infra/docker/docker-compose.yml down -v`
- if `KEEP_VOLUME=1`, do not remove volumes

✅ Done:
- `chmod +x scripts/*.sh && ./scripts/local_up.sh` succeeds
- `./scripts/local_down.sh` stops and cleans up

---

### 6) RUNBOOK update
Create/update `docs/RUNBOOK.md` with a short “Local OpenSearch v1.1” section (<= 8 lines):

Include:
- Start: `./scripts/local_up.sh`
- Check: `curl http://localhost:9200`
- Check aliases: `curl -s http://localhost:9200/_cat/aliases?v`
- Lexical smoke: a curl `_search` on `books_doc_read`
- Vector smoke: a curl `_search` on `books_vec_read`
- Stop: `./scripts/local_down.sh`

---

## Acceptance Tests (What to run)
1) `chmod +x scripts/*.sh`
2) `./scripts/local_down.sh`
3) `./scripts/local_up.sh`
4) `curl -s http://localhost:9200/_cat/aliases?v`
5) lexical smoke query returns hits >= 1
6) vector smoke query returns hits >= 1
7) `./scripts/local_down.sh`

---

## Output (in local summary)
- List created/updated files
- Copy-paste run commands
- Any known issues (ports, Docker memory)
