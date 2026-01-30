# Synonym Deployment Pipeline (Local)

This pipeline publishes a `synonym_set` version from MySQL, generates a mapping with embedded synonyms,
then triggers a safe reindex via the Index Writer service.

## Prereqs
- MySQL schema includes `synonym_set` (see `db/migration/V8__synonym_normalization.sql`).
- Index Writer service running on `http://localhost:8090`.
- `PyMySQL` installed (`python3 -m pip install -r scripts/ingest/requirements.txt`).

## Rule format
`synonym_set.rules_json` is expected to be JSON:
```json
{
  "ko": ["harry potter, 해리 포터"],
  "en": ["sci fi, science fiction"]
}
```
- If `rules_json` is a list, it is treated as Korean (`ko`) rules.
- Each entry is OpenSearch synonym syntax.

## Publish (create mapping + reindex)
```bash
python3 scripts/synonyms/publish_synonyms.py \
  --name books_synonyms_ko \
  --version v1
```

Optional flags:
- `--synonym-set-id 123`
- `--no-reindex` (only activate + generate mapping)
- `--activate-only` (only mark DB ACTIVE/ARCHIVED)
- `--material-kinds BOOK` (comma-separated)
- `--index-prefix books_doc_v1_syn`

## Rollback
Re-run with the previous version:
```bash
python3 scripts/synonyms/publish_synonyms.py \
  --name books_synonyms_ko \
  --version v0
```

This generates a new index with the previous synonym set and swaps aliases via the Index Writer job.

## Outputs
- Generated mapping: `infra/opensearch/generated/books_doc_v1_<name>_<version>.mapping.json`
- Reindex job: recorded in `reindex_job` (state machine + progress)
