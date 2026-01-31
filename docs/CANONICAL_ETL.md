# Canonical ETL (Incremental Upsert)

This runbook covers the raw_node → canonical load, quality validation, and minimal authority candidates.

## Prereqs
- MySQL schema applied through migrations (including `V15__ingest_checkpoint.sql` and `V16__authority_candidates.sql`).
- `PyMySQL` installed (`python3 -m pip install -r scripts/ingest/requirements.txt`).
- `raw_node` populated (see ingest pipeline).

## Run ETL (incremental)
```bash
python3 scripts/canonical/canonical_etl.py \
  --batch-id 123 \
  --batch-size 1000
```

Or use the wrapper script (runs ETL + quality checks by default):
```bash
./scripts/canonical/run_canonical_etl.sh
```

You can copy defaults from:
```bash
cp scripts/canonical/.env.example scripts/canonical/.env
set -a
source scripts/canonical/.env
set +a
```

Notes:
- If `--batch-id` is omitted, the latest `raw_node.batch_id` is used.
- Progress is stored in `ingest_checkpoint` per entity kind (`CONCEPT`, `AGENT`, `LIBRARY`, `MATERIAL`).
- Re-running is idempotent; unchanged payloads are skipped based on `last_payload_hash`.

## Quality validation
```bash
python3 scripts/canonical/validate_canonical.py
```
Checks:
- Required fields (id/type/hash) for agent/concept/material/library
- Orphan link rows (`material_agent`, `material_concept`)
- Basic distributions (material_kind, agent_type)

## Authority candidates (v1)
Build merge candidates and agent alias candidates:
```bash
python3 scripts/authority/build_candidates.py --rule-version v1
```

To include authority candidates in the wrapper script:
```bash
RUN_AUTHORITY=1 ./scripts/canonical/run_canonical_etl.sh
```
Optional filters:
- `--since-date YYYY-MM-DD`
- `--max-materials N`
- `--dry-run`

Tables:
- `material_merge_group` (OPEN groups + master selection)
- `agent_alias_candidate` (OPEN alias candidates)

These are **candidates only** and do not rewrite canonical tables.
