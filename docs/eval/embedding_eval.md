# Embedding Offline Eval

## Purpose
Evaluate embedding quality (vector-only or hybrid) by comparing baseline vs candidate models.

## Dataset
- `data/eval/embedding_queries.jsonl`
- Each line: `{ "qid": "...", "query": "...", "relevant_doc_ids": ["..."] }`

## Run
```bash
python3 scripts/eval/embedding_eval.py \
  --mis-url http://localhost:8005 \
  --os-url http://localhost:9200 \
  --baseline toy \
  --candidate multilingual-e5-small \
  --hybrid \
  --out data/eval/reports
```

## Output
- JSON + Markdown reports in `data/eval/reports/`
- Sample: `data/eval/reports/embedding_eval_sample.json`
