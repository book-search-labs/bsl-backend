# B-0310 — Embedding Text Builder v2 (도서 도메인 풍부화 + 정규화)

## Goal
Toy embedding의 입력이 되는 `vector_text`가 너무 단순(제목/저자/출판사)해서 의미 기반 검색 품질이 낮다.  
도서 도메인에 맞는 **풍부화된 텍스트 템플릿(vector_text_v2)** 과 정규화 규칙을 정의/구현하고, 재현/디버깅을 위해 vec 문서에 `vector_text_v2` 및 해시를 함께 저장한다.

## Why
- embedding 품질의 1차 결정요인은 모델보다 **입력 텍스트 구성**인 경우가 많다.
- 도서 검색은 제목/저자 외에도 시리즈/권차/주제/키워드/연도 등 신호가 중요하다.
- 향후 chunk/RAG로 확장할 때도 동일한 텍스트 스펙을 재사용할 수 있다.

## Scope
1) `build_vector_text_v2(record) -> str` 구현
- 권장 포함 필드(가능한 것만):
  - title_ko, title_en, subtitle/alt_title
  - authors (name_ko/name_en + role)
  - publisher_name
  - issued_year (있으면)
  - series_name + volume (있으면)
  - kdc / keywords / subjects (있으면)
  - identifiers (ISBN은 약하게; 가능하면 라벨만)
- 텍스트 템플릿은 **라벨드 포맷**(예: `TITLE_KO: ... | AUTHOR: ...`)으로 유지

2) 정규화 규칙
- NFKC, 공백 collapse, trim, (영문) lowercase
- 권차/숫자 표준화(예: 01권→1권, vol.1→1권)
- 특수기호 정리(도서 도메인에서 의미 없는 구분자는 공백화)

3) 저장 필드
- `vector_text_v2`: 원문 저장(디버깅)
- `vector_text_hash`: sha256(vector_text_v2) 저장(캐시/중복 방지에 사용)

## Non-goals
- 실제 embedding 모델 호출은 B-0311에서 처리
- chunk 기반 인덱싱/청킹은 B-0313(옵션)

## Interfaces / Contracts
Vector doc(books_vec_write)에 아래 필드 추가(또는 기존 필드 확장):
- `vector_text_v2`: text/keyword
- `vector_text_hash`: keyword

## Design Notes
- 텍스트는 “짧고 정보 밀도 높게” 구성하되, 모델이 이해하기 쉬운 라벨로 명확히 한다.
- ISBN은 과적합/노이즈 가능성이 있어 `IDENTIFIERS: ISBN13=...` 수준으로 약하게 포함(또는 옵션).
- title_ko/title_en이 모두 있으면 둘 다 포함하되 중복 제거.

## DoD (Definition of Done)
- 50~200개 샘플 레코드로 `vector_text` vs `vector_text_v2` 비교 산출물 생성:
  - `data/debug/vector_text_samples_v2.ndjson` (권장)
- ingest 실행 시 `books_vec_write`에 `vector_text_v2`, `vector_text_hash`가 함께 적재됨
- deadletter/체크포인트 동작에 영향 없음

## Files / Modules
- `scripts/ingest/ingest_opensearch.py` (vector_text 생성부 교체)
- (신규 권장) `scripts/ingest/vector_text.py` (builder/normalize 유틸)
- (필요 시) `contracts/opensearch/books_vec_mapping.json` (필드 반영)

## Commands (examples)
```bash
# 샘플 출력만 생성(옵션: --dry-run)
python scripts/ingest/ingest_opensearch.py --dataset book --limit 200 --dump-vector-text-v2

# 정상 ingest
ENABLE_VECTOR_INDEX=1 python scripts/ingest/ingest_opensearch.py
```

## Codex Prompt (copy/paste)
```text
Implement B-0310:
- Add build_vector_text_v2 for book vector docs with a labeled template and domain-specific fields (title_ko/en, authors with roles, publisher, issued_year, series+volume, kdc/keywords if present).
- Apply normalization: NFKC, whitespace collapse, trim, lowercase for English, volume canonicalization (01권->1권, vol.1->1권).
- Store vector_text_v2 and vector_text_hash(sha256) in books_vec docs.
- Keep checkpoints and deadletter behavior unchanged.
- Add an optional debug dump (ndjson) for ~200 samples to compare v1 vs v2.
```
