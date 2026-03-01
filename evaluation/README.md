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

## Chat recommendation experiment quality report

Use `scripts/eval/chat_recommend_eval.py` to generate periodic quality reports from QS metrics and optionally enforce a gate:

```bash
python3 scripts/eval/chat_recommend_eval.py \
  --metrics-url http://localhost:8001/metrics \
  --session-id u:101:default \
  --require-min-samples \
  --min-samples 20 \
  --max-block-rate 0.4 \
  --max-auto-disable-total 0 \
  --out data/eval/reports
```

To fail CI/local gate on threshold violation:

```bash
python3 scripts/eval/chat_recommend_eval.py \
  --metrics-url http://localhost:8001/metrics \
  --session-id u:101:default \
  --require-min-samples \
  --gate
```

`./scripts/test.sh`에서 옵션 게이트로 실행하려면:

```bash
RUN_CHAT_RECOMMEND_EVAL=1 ./scripts/test.sh
```

피드백/품질 루프를 한 번에 실행하려면:

```bash
./scripts/chat/run_recommend_quality_loop.sh
```

## Chat feedback aggregation -> backlog seeds

Use `scripts/chat/aggregate_feedback.py` to summarize feedback and generate actionable backlog seeds:

```bash
python3 scripts/chat/export_feedback_events.py \
  --since 2026-02-01T00:00:00+00:00 \
  --output evaluation/chat/feedback.jsonl

python3 scripts/chat/aggregate_feedback.py \
  --input evaluation/chat/feedback.jsonl \
  --output evaluation/chat/feedback_summary.json \
  --backlog-output evaluation/chat/feedback_backlog.json

python3 scripts/chat/render_feedback_backlog_md.py \
  --input evaluation/chat/feedback_backlog.json \
  --output tasks/backlog/generated/chat_feedback_auto.md
```
