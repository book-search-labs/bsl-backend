# T-0201 — OpenSearch local runtime + seed

## Goal
Run OpenSearch locally using Docker, create the `books_v1` index by applying
`infra/opensearch/books_v1.mapping.json`, then bulk-insert 5 sample book documents
so that search works end-to-end. Automate the entire flow with scripts.

---

## Must Read (SSOT)
- `AGENTS.md`
- `infra/opensearch/books_v1.mapping.json`
- `infra/opensearch/INDEX_VERSIONING.md` (if present, follow it)
- `docs/RUNBOOK.md` (create or update if missing)

---

## Scope

### Allowed
- `infra/**`
- `scripts/**`
- `docs/RUNBOOK.md`

### Forbidden
- `services/**`
- `contracts/**`
- `db/**`

---

## Environment Assumptions
- macOS/Linux (bash)
- Docker and Docker Compose installed
- Port collisions are possible (default port 9200). If ports are taken, fail with a clear error message.

---

## Implementation Requirements

### 1) `infra/docker/docker-compose.yml`
Configure OpenSearch as a single node.

- Service/container name: `opensearch`
- Ports:
  - `9200:9200` (HTTP)
  - `9600:9600` (Performance Analyzer)
- Required environment variables:
  - `discovery.type=single-node`
  - `plugins.security.disabled=true` (local dev convenience)
  - `OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m` (minimal heap)
- Add a healthcheck:
  - Use a `curl`-based check (e.g., cluster health)
- (Optional) Volume mount:
  - `opensearch-data:/usr/share/opensearch/data`

✅ Done check:
- `docker compose -f infra/docker/docker-compose.yml up -d`
- `curl http://localhost:9200` returns a valid OpenSearch response

---

### 2) `scripts/os_seed_books_v1.sh`
Purpose: “Create index + apply mapping + bulk insert sample docs + refresh + smoke check”

#### Script Requirements
- Bash with `set -euo pipefail`
- Configurable via environment variables:
  - `OS_URL` (default: `http://localhost:9200`)
  - `INDEX_NAME` (default: `books_v1`)
- Index lifecycle policy:
  - If the index exists:
    - Default: delete and recreate (local dev)
    - If `KEEP_INDEX=1`, do not delete (optional)
- Apply mapping:
  - Use `infra/opensearch/books_v1.mapping.json`
  - Create via `PUT /{index}`
- Bulk data:
  - Generate NDJSON in-script with a heredoc (or add a separate file if preferred)
  - Insert exactly 5 sample books with minimum fields:
    - `doc_id` (or `book_id`) : string
    - `title`: string
    - `authors`: array[string]
    - `publisher`: string
    - `publication_year`: int
  - Include at least one title containing “해리포터” (for smoke validation)
  - IMPORTANT: The Bulk payload **must be terminated by a newline** (`\n`)
- Refresh:
  - `POST /{index}/_refresh`
- Smoke check:
  - Run a simple search and report success if at least 1 hit is returned
  - Example: match query on `title` for `"해리"` (or `_search?q=해리`)
  - Print the result summary in logs

✅ Done check:
- Running `scripts/os_seed_books_v1.sh` results in:
  - Index created successfully
  - Bulk insert succeeds (no bulk errors)
  - Refresh succeeds
  - Smoke query shows `hits >= 1`

---

### 3) `scripts/local_up.sh`
Purpose: “Start OpenSearch + wait for readiness + run seed automatically”

#### Requirements
- Bash with `set -euo pipefail`
- Steps:
  1) `docker compose -f infra/docker/docker-compose.yml up -d`
  2) Poll health/readiness for up to 60 seconds (every 2 seconds)
  3) On success, execute `scripts/os_seed_books_v1.sh`
- Failure behavior:
  - If not ready within 60 seconds:
    - Print `docker compose logs opensearch --tail=200`
    - Exit non-zero

✅ Done check:
- One run of `scripts/local_up.sh` completes:
  - container up
  - readiness wait
  - seed
  - smoke check

---

### 4) `scripts/local_down.sh`
Purpose: “Compose down”

- Default:
  - `docker compose -f infra/docker/docker-compose.yml down -v` (remove volumes)
- Optional behavior:
  - If `KEEP_VOLUME=1`, run `down` without `-v`

✅ Done check:
- Running `scripts/local_down.sh` stops/removes containers (and volumes by default)

---

### 5) `docs/RUNBOOK.md` (keep it short — within ~5 lines of commands)
Must include:
- Prerequisite: Docker
- Start:
  - `./scripts/local_up.sh`
- Verify:
  - `curl http://localhost:9200`
  - `curl -XPOST http://localhost:9200/books_v1/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"title":"해리"}}}'`
- Stop:
  - `./scripts/local_down.sh`

---

## Acceptance Tests (What to run)
1) `chmod +x scripts/*.sh`
2) `./scripts/local_up.sh`
3) `curl http://localhost:9200`
4) Verify hits using the match query above
5) `./scripts/local_down.sh`

---

## Output (in PR description)
- List of created/updated files
- How to run (copy-paste commands)
- Any known issues (ports/memory requirements)
