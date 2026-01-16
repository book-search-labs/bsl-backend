# Normalization Rules (MVP)

This document defines the **deterministic, non-ML** normalization rules used by the Query Service (QS) to produce stable query strings for downstream search, logging, and caching.

The output of these rules is used to populate:
- `query.normalized`
- `query.canonical` (MVP: identical to `normalized`)

> **SSOT note:** Contracts in `contracts/` define the required fields. This document defines *how* QS should compute those fields for MVP.

---

## 1) Goals

Normalization should:

1. **Reduce input variance**
  - Treat visually/semantically equivalent strings as the same whenever possible.

2. **Be deterministic and fast**
  - No model calls; safe to run per keystroke if needed.

3. **Improve recall without breaking intent**
  - Do not delete meaningful characters (e.g., numbers, language-specific letters).
  - Prefer conservative transformations.

4. **Support stable caching**
  - Normalized strings should be stable keys for caches and analytics aggregation.

---

## 2) Definitions

- **raw**: the user input as received.
- **normalized**: the result after applying all rules in this document.
- **canonical**: the “best” query representation for retrieval and ranking.
  - MVP: `canonical == normalized`.
  - Future: `canonical` may incorporate spell correction and rewrites.

---

## 3) Rule Order (MVP)

Apply rules **in this exact order**:

1. Unicode normalization (NFKC)
2. Control character removal
3. Whitespace trimming
4. Whitespace collapsing
5. Optional punctuation normalization (very conservative)
6. Empty-string guard (return 400)

---

## 4) Rules (Detailed)

### Rule 1 — Unicode Normalization (NFKC)

**What**
- Apply Unicode **Normalization Form KC (NFKC)** to the whole string.

**Why**
- Converts compatibility characters to a consistent form.
- Reduces differences caused by half-width/full-width forms and certain composition variants.

**Examples**
- Full-width digits → ASCII digits: `１２３` → `123`
- Some compatibility characters normalize to a standard representation.

**Implementation hint (Python)**
- Use `unicodedata.normalize("NFKC", s)`.

---

### Rule 2 — Remove Control Characters

**What**
- Remove ASCII control characters:
  - `U+0000` to `U+001F`
  - `U+007F` (DEL)
- Keep normal spaces; remove invisible control codes that can poison logs and caching.

**Why**
- Prevents weird cache keys and log artifacts.
- Avoids accidental multi-line inputs, terminal escapes, etc.

**Examples**
- `"harry\u0007potter"` → `"harrypotter"` (bell removed)
- `"a\u001Bb"` → `"ab"` (ESC removed)

**Notes**
- Do **not** remove regular Unicode letters/symbols beyond control ranges in MVP.

---

### Rule 3 — Trim (Leading/Trailing Whitespace)

**What**
- Remove leading and trailing whitespace.

**Why**
- Users commonly type spaces; not meaningful for query semantics.

**Examples**
- `"  해리포터  "` → `"해리포터"`

---

### Rule 4 — Collapse Internal Whitespace

**What**
- Replace any run of whitespace characters (spaces, tabs, newlines) with a **single ASCII space**.

**Why**
- Prevents variance like `"해리   포터"` vs `"해리 포터"`.
- Maintains token boundaries.

**Examples**
- `"해리   포터"` → `"해리 포터"`
- `"a\tb\nc"` → `"a b c"`

**Implementation hint**
- Regex: `\s+` → `" "` after trimming.

---

### Rule 5 — Conservative Punctuation Normalization (Optional in MVP)

This rule is **optional**. Only enable if you are confident it does not reduce intent.

**What (conservative)**
- Normalize common quote variants to ASCII quotes:
  - `“ ”` → `"`
  - `‘ ’` → `'`
- Normalize repeated punctuation sequences:
  - `!!!` → `!`
  - `???` → `?`

**Why**
- Improves stability without changing core tokens.

**What NOT to do in MVP**
- Do not remove punctuation broadly (e.g., removing `-`, `:`) because it can carry meaning:
  - `"C++"` vs `"C"`
  - `"2020-2021"` vs `"2020 2021"`
- Do not aggressively strip symbols in non-Latin languages.

---

### Rule 6 — Empty-String Guard

**What**
- If the result after Rule 1–5 is an empty string, return **HTTP 400**.

**Why**
- Prevents meaningless downstream work and broken analytics.

**Examples**
- raw = `"   "` → 400
- raw = `"\n\t"` → 400

---

## 5) Output Mapping to QueryContext

Given input `raw`, QS must populate:

- `query.raw` = raw input exactly as received (string)
- `query.normalized` = result after applying Rules 1–6
- `query.canonical` = MVP: same as normalized

Additionally (MVP defaults):
- `query.tokens` = `query.normalized.split(" ")` with empty tokens removed
- `query.language.detected` = `"ko"` (default)
- `query.language.confidence` = `0.5` (default)

---

## 6) Examples

### Example A
- raw: `"  해리   포터  1권  "`
- normalized: `"해리 포터 1권"`
- canonical: `"해리 포터 1권"`
- tokens: `["해리", "포터", "1권"]`

### Example B
- raw: `"１２３  \n  ABC"`
- NFKC: `"123  \n  ABC"`
- normalized: `"123 ABC"`

### Example C (empty)
- raw: `" \t\n "`
- normalized: `""` → return 400

---

## 7) Non-Goals (Explicitly Out of Scope for MVP)

The following are **not** part of MVP normalization and should be implemented later:

- Spell correction (T5 / dictionary-based)
- Synonym expansion
- Query rewriting (LLM rewrite)
- Language identification (LID) with a real model
- Morphological analysis (e.g., Korean tokenizers)
- Transliteration / cross-lingual normalization
- Stopword removal

---

## 8) Testing Recommendations

At minimum, add unit tests covering:
- whitespace collapse
- NFKC normalization on full-width digits
- control character removal
- empty-string guard (400)

---

## 9) Implementation Notes (Python)

Recommended implementation approach:
- Use `unicodedata.normalize("NFKC", s)`
- Remove control characters via a small translation/filter
- Apply `.strip()`
- Apply regex whitespace collapse with `re.sub(r"\s+", " ", s)`

Keep it small and deterministic. Performance matters.
