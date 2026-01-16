# Runbook (Local)

This file is **documentation**. Run the commands by copy/pasting the code blocks into your terminal.

Prerequisite: Docker / Docker Compose

---

## Start (includes seed)

Copy/paste into your terminal:

```bash
chmod +x scripts/*.sh
./scripts/local_up.sh
```

## Verify
```bash
curl -s "http://localhost:9200"
curl -s -XPOST "http://localhost:9200/books_v1/_count?pretty"
curl -s -XPOST "http://localhost:9200/books_v1/_search" \
-H "Content-Type: application/json" \
-d '{"query":{"match":{"title":"해리"}},"size":3}'
```

## Stop
```bash
./scripts/local_down.sh
```
