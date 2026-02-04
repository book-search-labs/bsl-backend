# Evaluation Assets

Offline evaluation datasets and sample runs for LTR regression checks.

## Files

- `queries.jsonl`: query id + text + set (golden/shadow/hard)
- `judgments.jsonl`: relevance labels per query/doc
- `runs/`: sample ranked runs (`sample_run.jsonl`)
- `eval_runs/`: generated metric reports (`*.json`)
- `baseline.json`: baseline metrics used by CI gate

## Run eval locally

```bash
python3 scripts/eval/run_eval.py --run evaluation/runs/sample_run.jsonl \
  --output evaluation/eval_runs/sample.json \
  --write-baseline evaluation/baseline.json
```

## Run with regression gate

```bash
python3 scripts/eval/run_eval.py --run evaluation/runs/sample_run.jsonl \
  --baseline evaluation/baseline.json --gate
```

## Rerank config before/after report

Use `scripts/eval/rerank_eval.py` to compare rerank settings (for example stage2-only vs stage1+stage2):

```bash
python3 scripts/eval/rerank_eval.py \
  --queries data/eval/rerank_queries.jsonl \
  --baseline-mode rerank \
  --baseline-rerank-options '{"model":"rerank_toy_v1","rerank":{"stage1":{"enabled":false},"stage2":{"enabled":true,"topK":50}}}' \
  --candidate-mode rerank \
  --candidate-rerank-options '{"model":"rerank_ltr_baseline_v1","rerank":{"stage1":{"enabled":true,"topK":30},"stage2":{"enabled":true,"topK":10}}}' \
  --out evaluation/eval_runs
```
