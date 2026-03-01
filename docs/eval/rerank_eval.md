# Rerank Offline Eval

## Purpose
Measure rerank quality improvements and guard against regressions.

## Dataset
- `data/eval/rerank_queries.jsonl`
- Each line: `{ "qid": "...", "query": "...", "relevant_doc_ids": ["..."], "set": "hard|shadow" }`

## Run
```bash
python3 scripts/eval/rerank_eval.py \
  --mis-url http://localhost:8005 \
  --ranking-url http://localhost:8082 \
  --os-url http://localhost:9200 \
  --rerank-topk 50 \
  --out data/eval/reports
```

## Regression gate
```bash
python3 scripts/eval/rerank_eval.py \
  --baseline-report data/eval/reports/rerank_eval_sample.json \
  --gate
```

Or via test script:
```bash
RUN_RERANK_EVAL=1 ./scripts/test.sh
```

## Output
- JSON + Markdown reports in `data/eval/reports/`
- Sample: `data/eval/reports/rerank_eval_sample.json`
