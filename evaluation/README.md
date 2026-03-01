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

기본 실행 시 루프 전/후 추천 실험 스냅샷이 함께 저장된다:
- `evaluation/chat/recommend_experiment_snapshot_before.json`
- `evaluation/chat/recommend_experiment_snapshot_after.json`
- `evaluation/chat/rollout_snapshot_before.json`
- `evaluation/chat/rollout_snapshot_after.json`

실험 설정/상태를 운영에서 빠르게 조정하려면:

```bash
python3 scripts/chat/recommend_experiment_ops.py snapshot
python3 scripts/chat/recommend_experiment_ops.py config --payload-json '{"overrides":{"diversity_percent":70,"max_block_rate":0.35}}'
python3 scripts/chat/recommend_experiment_ops.py reset --payload-json '{"clear_overrides":true}'
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
  --backlog-output evaluation/chat/feedback_backlog.json \
  --allow-empty

python3 scripts/chat/render_feedback_backlog_md.py \
  --input evaluation/chat/feedback_backlog.json \
  --output tasks/backlog/generated/chat_feedback_auto.md

python3 scripts/chat/sync_feedback_backlog_tickets.py \
  --input evaluation/chat/feedback_backlog.json \
  --output-dir tasks/backlog/generated/feedback
```

`--allow-empty`를 사용하면 피드백 이벤트가 0건이어도 summary/backlog가 빈 payload로 갱신되어
이전 실행에서 남은 산출물이 stale 상태로 유지되지 않는다.
