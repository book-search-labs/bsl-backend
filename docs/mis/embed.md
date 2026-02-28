# MIS Embed API

## Endpoint
`POST /v1/embed`

Request:
```json
{ "model": "bge-m3", "normalize": true, "texts": ["...", "..."] }
```

Response:
```json
{ "version": "v1", "trace_id": "...", "request_id": "...", "model": "bge-m3", "dim": 768, "vectors": [[...],[...]] }
```

## Quick Start (bge-m3 ONNX)

1) Place artifacts:

```
models/
  embed/
    bge-m3/
      model.onnx
      tokenizer.json
```

2) Run MIS with embed backend:

```bash
./scripts/mis/run_mis_embed.sh
```

3) Smoke test:

```bash
./scripts/mis/embed_smoke_test.sh
```

## Configuration
- `MIS_EMBED_BACKEND=toy|onnx`
- `MIS_EMBED_MODEL_ID` (label expected in requests)
- `MIS_EMBED_MODEL_PATH` (onnx file path)
- `MIS_EMBED_TOKENIZER_PATH` (tokenizer.json path)
- `MIS_EMBED_OUTPUT_NAME` (optional output name override)
- `MIS_EMBED_DIM` (toy only; onnx uses model output)
- `MIS_EMBED_MAX_LEN` (token truncation)
- `MIS_EMBED_BATCH_SIZE` (max texts per request)
- `MIS_EMBED_NORMALIZE` (default normalize)

## Notes
- If `MIS_EMBED_BACKEND=onnx`, both model and tokenizer paths are required.
- Requests larger than `MIS_EMBED_BATCH_SIZE` return 413.
- Search Service should use:
  - `EMBEDDING_MODE=HTTP`
  - `EMBEDDING_BASE_URL=http://localhost:8005`
  - `EMBEDDING_MODEL=bge-m3`
