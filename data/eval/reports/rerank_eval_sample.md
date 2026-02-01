# Rerank Eval Report (fused_rrf -> rerank)

## Summary

| Metric | Baseline | Candidate | Diff |
| --- | --- | --- | --- |
| ndcg_10 | 0.5200 | 0.6400 | +0.1200 |
| mrr_10 | 0.4700 | 0.5800 | +0.1100 |
| recall_100 | 0.6900 | 0.8000 | +0.1100 |
| zero_result_rate | 0.0800 | 0.0300 | -0.0500 |

## Rerank stats
- rerank_call_rate: 0.720
- rerank_latency_ms_avg: 85.0
- rerank_latency_ms_p50: 70.0
- rerank_latency_ms_p95: 180.0

## Improved cases
- r001: harry potter philosopher stone (\u0394NDCG=+0.3100)

## Regressed cases

