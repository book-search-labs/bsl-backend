# MIS Rerank API

## Endpoint
`POST /v1/score`

Request (cross-encoder example):
```json
{
  "version": "v1",
  "trace_id": "...",
  "request_id": "...",
  "model": "rerank_ce_v1",
  "task": "rerank",
  "pairs": [
    { "pair_id": "b1", "query": "해리포터", "doc": "TITLE: 해리포터 ..." }
  ]
}
```

## Cross-encoder backend
Set the model registry entry:
- `backend: onnx_cross`
- `artifact_uri`: ONNX model path
- `tokenizer_uri`: tokenizer.json path
- `max_len`: max sequence length
- `logit_index`: which logit to use when output has multiple classes

## Notes
- For `onnx_cross`, `doc` text is required in each pair.
- Use guardrails in ranking-service to cap topR and timeouts.
