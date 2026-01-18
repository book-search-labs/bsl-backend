# B-0213 — Search Service: Autocomplete API (v1) backed by OpenSearch aliases

## Goal
Add a **minimal Autocomplete API** to **Search Service (Spring Boot)** so clients can request suggestions while typing.

After this ticket:
- Search Service exposes `GET /autocomplete`
- Endpoint queries OpenSearch using **read aliases** seeded by **B-0211**:
  - `books_ac_authors_read`
  - `books_ac_series_read`
- Optional (if mapping exists):
  - `books_doc_read` using `title_ko.edge` (or equivalent) for title suggestions
- Returns a stable JSON response:
  - `prefix`, `took_ms`
  - `items[]` with `{ type, text, score?, payload? }`

Non-goals:
- No new OpenSearch indices in this ticket
- No Query Service dependency
- No personalization
- No analytics/log pipeline

---

## Must Read (SSOT)
- `AGENTS.md`
- Existing `OpenSearchGateway` and request/timeout patterns
- Local OpenSearch alias status:
  - `curl -s "http://localhost:9200/_cat/aliases?v" | grep books_`

---

## Scope

### Allowed
- `services/search-service/**`
- `docs/RUNBOOK.md` (optional: add a short curl snippet)

### Forbidden
- `services/query-service/**`
- `apps/**`
- `contracts/**`
- `infra/**`
- `db/**`

---

## API

### Endpoint
- `GET /autocomplete`

### Query Params
- `q` (string, required): user-typed prefix
- `size` (int, optional, default 10, clamp 1..20)
- `types` (optional, comma-separated): `title,author,series`
  - default: `title,author,series`
- `debug` (bool, optional, default false)

### Response (v1)
```json
{
  "prefix": "해리",
  "items": [
    { "type": "title", "text": "해리 포터", "score": 1.0 },
    { "type": "author", "text": "J.K. 롤링", "score": 0.9 },
    { "type": "series", "text": "해리 포터 시리즈", "score": 0.8 }
  ],
  "took_ms": 12,
  "debug": {
    "sources": ["title","author","series"],
    "queries": {
      "author": { "index_alias": "books_ac_authors_read" },
      "series": { "index_alias": "books_ac_series_read" },
      "title": { "index_alias": "books_doc_read", "field": "title_ko.edge" }
    },
    "errors": []
  }
}
```

Notes:
- `score` may be heuristic/normalized; `null` is acceptable.
- `payload` is optional and can include ids if available in the ac docs.

---

## Implementation Requirements

### 1) DTOs
Create under existing API DTO package:
- `AutocompleteResponse`
- `AutocompleteItem`
  - fields: `type`, `text`, `score`, `payload`

Suggested types:
- `type`: enum `TITLE|AUTHOR|SERIES` (serialize as `title/author/series` or keep consistent)
- `payload`: `Map<String,Object>` (optional)

### 2) Controller
Create `AutocompleteController`:
- `@GetMapping("/autocomplete")`
- Validate:
  - `q` present and not blank
  - `size` clamped 1..20
  - `types` parsed to a set (default all)
- Measure `took_ms`

Return HTTP 200 always (MVP):
- If OpenSearch is unavailable, return empty `items` and include debug errors when `debug=true`.

### 3) OpenSearchGateway additions
Add methods (names flexible):
- `autocompleteAuthors(prefix, size, timeBudgetMs): List<AutocompleteItem>`
- `autocompleteSeries(prefix, size, timeBudgetMs): List<AutocompleteItem>`
- Optional:
  - `autocompleteTitles(prefix, size, timeBudgetMs): List<AutocompleteItem>`

Index aliases (read-only):
- Authors: `books_ac_authors_read`
- Series: `books_ac_series_read`
- Titles (optional): `books_doc_read`

Query strategy (MVP):
- Prefer `match_phrase_prefix` when the field is analyzed text
- Or `prefix` query if the field is keyword / edge-ngram keyword
- Keep it fast: small `size` and `terminate_after` if you already use it
- Use a short timeout (e.g., 200ms default; clamp 50..500ms)

### 4) Merging / de-dup
- Combine lists from requested types
- De-dupe by `(type, normalizedText)` where `normalizedText = trim().toLowerCase()`
- Fill final list up to `size`:
  - simple order: title → author → series
  - OR score sort if you have comparable scores

### 5) Error handling
- Each source call should be isolated:
  - if authors fails, still return series (and title if enabled)
- For failures, store a small string in debug:
  - `{ "source": "author", "error": "OpenSearchUnavailableException" }`

### 6) Local run docs (optional)
Add to `docs/RUNBOOK.md`:
```bash
curl -s "http://localhost:8080/autocomplete?q=해리&size=10&types=title,author,series&debug=true" | jq .
```

---

## Acceptance Tests

### Pre-req
- OpenSearch running locally
- Aliases exist:
```bash
curl -s "http://localhost:9200/_cat/aliases?v" | grep books_
```
Expected includes at least:
- `books_ac_authors_read`
- `books_ac_series_read`

### Run Search Service
```bash
cd services/search-service
./gradlew bootRun
```

### Verify
1) Basic:
```bash
curl -s "http://localhost:8080/autocomplete?q=해리" | jq .
```
- HTTP 200
- `prefix == "해리"`
- `items` is an array (possibly empty)

2) Types filter:
```bash
curl -s "http://localhost:8080/autocomplete?q=해리&types=author&size=5" | jq .
```
- only `type == "author"` items

3) Debug:
```bash
curl -s "http://localhost:8080/autocomplete?q=해리&debug=true" | jq .
```
- debug shows sources + any errors

---

## Deliverables (Dev Summary)
- Changed/created files list
- How to run locally
- Curl examples and expected behavior
- Known limitations (no popularity ranking, no personalization)
