# B-0354 — 다국어 질의 품질 보강 (한글 우선 + CJK 혼합 질의)

## Goal
한국어 중심 서비스에 맞게 다국어(한글/한자/영문 혼합) 질문 품질을 개선한다.

## Why
- 현재 CJK 혼합 쿼리에서 의도 파악과 근거 검색 실패율이 높음
- 카탈로그 특성상 동일 도서의 다국어 표기가 혼재됨

## Scope
### 1) Normalize/Rewrite 강화
- NFKC/공백/기호 정규화
- 한글 우선 rewrite 룰 + 필요 시 원문 병행 검색

### 2) Retrieval routing 개선
- 한국어 title/author/publisher 필드 가중치 강화
- 한자/중문 표기 fallback 경로 유지

### 3) 랭킹 정책
- 동일 점수대에서 한국어 metadata 우선 정렬
- 카테고리 브라우징 연계 시 locale-aware boost

### 4) 평가셋
- "영어교육", "문화지도" 등 실제 실패 쿼리 포함
- 혼합 질의 회귀셋 자동 테스트

## DoD
- 한국어 의도 질의에서 한국어 도서가 상단에 노출
- 기존 다국어 검색 recall 유지
- 회귀셋 기준 precision/recall 목표 충족

## Codex Prompt
Improve multilingual chat retrieval quality:
- Add Korean-first normalization/rewrite and CJK fallback routing.
- Apply locale-aware ranking preference for Korean metadata.
- Add regression cases for mixed-language queries.
