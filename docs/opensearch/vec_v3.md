# Vector Index v3 (books_vec_v3)

> Legacy profile (`bge-m3`, 1024-d). Current default profile is `books_vec_v4` (384-d).

## Defaults
- `dimension`: 1024 (`bge-m3` aligned)
- `space_type`: `cosinesimil`
- HNSW: `m=16`, `ef_construction=128`, `ef_search=100`

You can override these when bootstrapping:

```bash
VEC_DIM=1024 VEC_SPACE_TYPE=cosinesimil VEC_HNSW_M=16 VEC_HNSW_EF_CONSTRUCTION=128 VEC_HNSW_EF_SEARCH=100 \
  bash scripts/os_bootstrap_indices_v1_1.sh
```

## Quick verification

```bash
curl -sS "$OS_URL/books_vec_read/_search" \
  -H 'Content-Type: application/json' \
  -d '{"size":3,"query":{"knn":{"embedding":{"vector":[0.1,0.2],"k":3}}}}'
```
