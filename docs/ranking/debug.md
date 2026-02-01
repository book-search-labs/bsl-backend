# Ranking Debug/Explain

## Enable debug
Send `options.debug=true` to `/rerank`.

Example request:
```json
{
  "query": {"text": "harry potter"},
  "candidates": [
    {"doc_id": "b1", "doc": "TITLE: ...", "features": {"rrf_score": 0.2, "lex_rank": 1}}
  ],
  "options": {"size": 10, "debug": true, "timeout_ms": 200}
}
```

## Debug payload
- Per hit: `debug.raw_features`, `debug.features`, `debug.reason_codes`
- Top-level: `debug.model_id`, `debug.feature_set_version`, `debug.candidates_in/used`, `debug.rerank_applied`
- `debug.replay`: normalized request snapshot for replay

## Replay
Save `debug.replay` and POST it back to `/rerank` for deterministic reproduction.

