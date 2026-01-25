# B-0220 — Ingest NLK LOD JSON(-LD) datasets into MySQL + OpenSearch (streaming, local-first)

> Goal: make **“download → unzip → one command → DB + OpenSearch populated”** work for ~10GB+ of NLK dataset files, without loading whole files into memory.

---

## Why this ticket exists

Right now we can bootstrap OpenSearch indices, but we **don’t ingest any NLK datasets** into:
- **MySQL** (source-of-truth / staging)
- **OpenSearch** (searchable docs + autocomplete seed)

This ticket establishes the **local ingestion pipeline** (streaming parser + bulk loaders) and the **expected on-disk data layout** so Codex can run it deterministically.

---

## Important correction: this is not “pure NDJSON” in the NLK download

The NLK “JSON-LD” downloads are typically shaped like:

- a **single JSON object** containing:
  - `"@graph": [ {node1}, {node2}, ... ]`
  - `"@context": { ... }`

That format is **JSON-LD graph container**, not NDJSON (newline-delimited JSON).  
Some “JSON” datasets may still be JSON-LD-ish or a similar container; do not assume 1-line-per-record.

✅ **Implementation requirement:** the ingest tool must support both:
1) **JSON-LD graph container** (`{"@graph":[...], "@context":{...}}`)
2) **NDJSON** (if we pre-split later): one JSON object per line

Auto-detect format per file.

---

## Data location contract (what Codex should assume)

### Default directory (repo-local, ignored by git)

Place all downloaded/unzipped NLK files under:

```
<repo-root>/
  data/
    nlk/
      raw/
        Offline_0.json ... Offline_35.json
        Online_0.json  ... Online_108.json
        Person_0.json  ... Person_9.json
        Organization_0.json ... Organization_1.json
        Concept_0.json ... Concept_2.json
        Library_0.json
        book.json
        audiovisual.json
        govermentpublication.json
        serial.json
        thesis.json
```

**Rules**
- `data/nlk/**` must be **gitignored**.
- The ingest scripts must accept `NLK_DATA_DIR` to override the base dir.
  - Default: `NLK_DATA_DIR=./data/nlk`
  - Raw files live in `${NLK_DATA_DIR}/raw`

> This answers “Codex가 파일을 어디에 있다고 아느냐?”  
> Codex will only “know” what we write in this ticket: **`${NLK_DATA_DIR:-./data/nlk}/raw`**.

---

## Scope

### 1) Local infra: add MySQL to docker-compose and scripts
- Extend `docker-compose.yaml` to include:
  - `mysql:8` service
  - volumes + healthcheck
  - standard ports (`3306:3306`)
- Update `scripts/local_up.sh` and `scripts/local_down.sh` to start/stop mysql too.
- Provide `scripts/wait_mysql.sh` and `scripts/wait_opensearch.sh` (or similar) used by ingestion.

### 2) DB schema: run existing Flyway migrations
- Use the **existing Flyway migrations already in the repo** (do NOT invent a new schema unless missing).
- Add a script `scripts/db_migrate.sh` that:
  - waits for mysql
  - runs Flyway migration via the project’s existing mechanism (Gradle task or Flyway CLI)
- If Flyway config isn’t runnable in local, add a minimal “dev-only” Flyway container in compose (still sourcing the existing migration files).

### 3) Streaming ingest tool (Python recommended for speed of iteration)
Implement a single entrypoint:

`tools/ingest/ingest_nlk.py`

Capabilities:
- Input: `${NLK_DATA_DIR}/raw/*.json` (large files)
- Auto-detect file format:
  - if it looks like a JSON object with `"@graph"` → stream over `@graph[]`
  - else → treat as NDJSON stream (line by line)
- For each node/record:
  - extract stable keys:
    - `@id` (string)
    - `@type` (string or array)
  - write to MySQL **staging/raw** table(s)
  - optionally emit to OpenSearch bulk API for relevant types

**Hard requirement:** no full-file `json.load()` for multi-GB files.

Suggested parsing:
- JSON-LD graph container: `ijson` streaming over `@graph.item`
- NDJSON: read line by line + `orjson.loads`

### 4) Minimal MySQL staging table (only if not already in Flyway)
If Flyway already has staging/raw tables, use them.  
If not, add **one minimal staging table** via Flyway (new migration) *only as a fallback*:

`nlk_raw_node`
- `id` (varchar PK) — `@id`
- `type` (varchar) — first `@type`
- `source` (varchar) — dataset name/file group (offline/online/person/…)
- `payload` (json) — raw node
- `ingested_at` (timestamp)
- optional: `hash` (char(64)) for idempotency

### 5) OpenSearch indexing (smoke-level, not final ranking)
- Insert a **minimal** searchable document set into the existing “books_doc” (or a dedicated staging index if safer).
- For Phase-0 search to work, index only what we can confidently map now:
  - Offline/Online material/work nodes (whatever dataset calls them) → `title`, `identifier`, `authors` (if present), `subjects` (if present)
- Use `_bulk` with batching and retry.

> The goal here is **“검색이 일단 됨”** (smoke), not perfect canonicalization.  
> Canonical model extraction + enrichment can be separate tickets (B-0221+).

---

## Non-goals (out of scope for B-0220)
- Full RDF triple-store / SPARQL engine
- Full canonical graph merge / authority resolution
- Embedding generation / vector indexing
- Ranking models / feature store / Kafka pipelines (later phases)

---

## Deliverables (files to add/change)

### Compose / scripts
- `docker-compose.yaml` — add mysql service
- `scripts/local_up.sh` — start mysql + wait + migrate + ingest
- `scripts/local_down.sh` — stop mysql + volumes optionally
- `scripts/db_migrate.sh`
- `scripts/ingest_nlk.sh` (wrapper around python tool)
- `.gitignore` — add `data/nlk/**`

### Ingest tool
- `tools/ingest/ingest_nlk.py`
- `tools/ingest/requirements.txt` (e.g., `ijson`, `orjson`, `pymysql`/`mysqlclient`, `requests`)
- `docs/RUNBOOK.md` — “데이터 내려받기/경로/실행” 업데이트

---

## Acceptance criteria (Definition of Done)

1. `./scripts/local_up.sh` brings up:
   - OpenSearch healthy
   - MySQL healthy
   - Flyway migrations applied (no errors)
2. With NLK files present in `${NLK_DATA_DIR:-./data/nlk}/raw`, running:
   - `./scripts/ingest_nlk.sh`
   ingests at least:
   - MySQL: `nlk_raw_node` (or existing staging tables) row count increases
   - OpenSearch: `books_doc_*` (or staging index) has documents
3. Smoke checks:
   - MySQL:
     - `SELECT COUNT(*) FROM nlk_raw_node;` returns > 0 (or equivalent table)
   - OpenSearch:
     - `_cat/indices` shows target index green/yellow
     - `_search` on the index returns hits
4. Resource safety:
   - ingestion runs in streaming mode (no OOM on multi-GB files)
   - bulk requests batch size configurable (defaults sane)

---

## Runbook snippet (local)

1) Put datasets here:
```
mkdir -p data/nlk/raw
# copy/unzip NLK JSON/JSON-LD files into data/nlk/raw
```

2) Start infra + migrate:
```
./scripts/local_up.sh
```

3) Ingest:
```
NLK_DATA_DIR=./data/nlk ./scripts/ingest_nlk.sh
```

---

## Codex prompt (English) — copy/paste

**Task:** Implement ticket **B-0220** described in `B-0220-ingest-ndjson-to-mysql-opensearch.md`.

You must:
1) Update `docker-compose.yaml` to add a MySQL 8 service (with volume + healthcheck + exposed 3306).
2) Update `scripts/local_up.sh` and `scripts/local_down.sh` so local_up brings up OpenSearch + MySQL, waits for health, runs Flyway migrations (using existing migrations already in the repo), then runs ingestion (optional step behind a flag like `ENABLE_INGEST=1`).
3) Add `.gitignore` rule for `data/nlk/**`.
4) Create a streaming ingestion tool `tools/ingest/ingest_nlk.py` that reads NLK dataset files from `${NLK_DATA_DIR:-./data/nlk}/raw`.
   - IMPORTANT: NLK files are often **JSON-LD graph containers**: a single JSON object with `"@graph": [ ... ]` and `"@context": {...}`. This is NOT NDJSON.
   - The tool must auto-detect per file:
     - If it contains `"@graph"` at the top-level, stream over `@graph.item` using a streaming parser (e.g., `ijson`).
     - Otherwise, treat it as NDJSON (one JSON object per line).
   - For each node, extract `@id` and `@type` and insert into a MySQL staging/raw table (use existing Flyway tables if present; otherwise add a minimal `nlk_raw_node` table via a new Flyway migration).
   - Also bulk-index a minimal searchable document set into OpenSearch (smoke-level), using `_bulk` batching and retries.
5) Update `docs/RUNBOOK.md` with:
   - where to put files: `data/nlk/raw/*`
   - how to run: `./scripts/local_up.sh` then `./scripts/ingest_nlk.sh`

Constraints:
- Must be safe for ~10GB total dataset: NO full-file json.load.
- Configurable batch sizes and concurrency via env vars.
- Provide smoke check commands in RUNBOOK.

Output:
- Commit only files in scope above.
- Ensure scripts are executable and work on macOS + Linux.

