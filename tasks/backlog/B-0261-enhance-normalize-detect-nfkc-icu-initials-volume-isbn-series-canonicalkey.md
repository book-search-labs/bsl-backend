# B-0261 — QS Normalize/Detect Enhanced (NFKC/ICU + Ultra-Performance/Character/ISBN/Series + canonicalKey)

## Goal
Strengthen the normalize/detect** to stabilize the book domain input into the operating type.

- NFKC/ICU Standard Normalization
- Ultra-Sensitive Search/ISBN/Character/Series Pattern Detection
- canonicalKey(=Remove duplicate/remove/grouping key)
- Provides a signal (confidence/flags) for SR/RS

## Background
- The book search is very large to enter:
  - Paste/Stage/Stage/Stage/Stage/Stage(01 ticket/vol.1/I)
  - )())
  - ISBN Hyphen/Public
- The quality/cass/log aggregates are all broken in downstream when shaken.

## Scope
### 1) Normalize rules (deterministic)
- Unicode:
  - NFKC Apply (All-in-one/Return/Return)
- whitespace:
  - trim + collapse multi-spaces
- punctuation:
  - The meaningless separator is blank unification (·   - : etc.)
  - (C++, C#, etc.)
- casing:
  - Lowercase
- numbers/volume:
  - "01", "vol.1", "1", "I" → "1"
  - Detected.volume

### 2) Detect rules
- isbn:
  - 10/13 digits, sensing patterns with hyphen
  - ISBN-10 check digit(X) case processing(optional)
- chosung:
  - mode=chosung in a single-digit self-confidence ratio
- mixed:
  - Detecting the jungle + English
- series hints:
  - "series", "set", "full version", "full ticket" etc. keywords
  - ":" After-sales service(optional)

### 3) canonicalKey generation (v1)
- Objective: The input of the same intention is the same key
- Price:
  - base = normalize(q_norm) + (volume?) + (isbn?) + (mode)
  - canonicalKey = sha256(base) or normalized string
- Scots Gaelic News
  - Cache Key, Log In Key, authority/merge hint

### 4) Test cases (must-have)
- Fixed at least 30 inputs→Output case table with fixtures
  - Hypersensitivity, Recommendation, ISBN, Mixed, All-in-one, Special characters
- Regression test included in CI

## Non-goals
- spell/LLM rewrite 2-pass (B-0262/0263)
- query cache (B-0264)

## DoD
- normalize/detect rule implementation + passing fixtures test
- Detected/confidence/canonicalKey in QueryContext v1
- edge case (secret/chart/ISBN) minimum 30 revolving test presence
- Performance: 1-pass p95 < 10~15ms target (local standard)

## Observability
- metrics:
  - qs_detect_mode_total{mode}
  - qs_isbn_detect_total
  - qs_volume_detect_total
- logs:
  - request_id, canonicalKey, detected.mode, detected.volume?

## Codex Prompt
Implement QS normalize/detect:
- Add deterministic normalization pipeline (NFKC/whitespace/punct/case).
- Add detect for isbn/chosung/mixed and volume canonicalization.
- Generate canonicalKey and include in QueryContext v1.
- Create fixture-based regression tests (30+ cases) and wire into CI.
