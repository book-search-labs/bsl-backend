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
