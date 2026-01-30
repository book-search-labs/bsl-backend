# Normalization Deployment Pipeline (Local)

This pipeline publishes a `normalization_rule_set` version from MySQL and writes an
active rules file that Query Service can read at startup.

## Prereqs
- MySQL schema includes `normalization_rule_set` (see `db/migration/V14__normalization_rule_set.sql`).
- `PyMySQL` installed (`python3 -m pip install -r scripts/ingest/requirements.txt`).

## Rule format
`normalization_rule_set.rules_json` should be JSON:
```json
{
  "replacements": [
    {"pattern": "sci fi", "replacement": "science fiction"},
    {"pattern": "\\s+", "replacement": " ", "regex": true}
  ]
}
```

## Publish
```bash
python3 scripts/normalization/publish_normalization.py \
  --name books_normalization \
  --version v1
```

Output file defaults to:
- `var/normalization/normalization_active.json`

To use in Query Service, set:
```bash
export NORMALIZATION_RULES_PATH=../var/normalization/normalization_active.json
```

## Rollback
Re-run with the previous version. This overwrites the active rules file.
