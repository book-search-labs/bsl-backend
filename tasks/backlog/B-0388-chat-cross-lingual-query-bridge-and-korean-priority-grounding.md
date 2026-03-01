# B-0388 — Chat Cross-lingual Query Bridge + Korean-priority Grounding

## Priority
- P2

## Dependencies
- B-0354, B-0361, B-0368

## Goal
다국어/혼합어 질의에서 한국어 중심 결과를 우선 제공하면서도 의미 손실 없이 cross-lingual 질의를 안정 처리한다.

## Scope
### 1) Query bridge
- 입력 언어 감지 + 한국어 pivot rewrite
- 원문 질의와 변환 질의를 병행 retrieval

### 2) Korean-priority ranking
- 한국어 문서 우선 가중치 적용
- 도메인 키워드(주문/환불/배송) 보존 규칙

### 3) Citation parity
- 번역/재작성된 주장과 원문 근거 간 연결 유지
- cross-lingual entailment mismatch 차단

### 4) Fallback policy
- 변환 불확실 시 원문 기반 답변 + 추가질문
- 고위험 인텐트는 보수적 응답

## Observability
- `chat_crosslingual_bridge_total{lang_pair}`
- `chat_korean_priority_rank_boost_total`
- `chat_crosslingual_citation_mismatch_total`
- `chat_crosslingual_fallback_total{reason}`

## Test / Validation
- 다국어 회귀셋(ko/zh/en 혼합) 평가
- 한국어 우선 정렬 정확성 테스트
- 번역 후 근거 정합성 테스트

## DoD
- 혼합어 질의 recall/groundedness 개선
- 한국어 우선 노출 정책 안정화
- cross-lingual 근거 불일치 감소

## Codex Prompt
Strengthen multilingual chat retrieval with Korean priority:
- Bridge cross-lingual queries through Korean pivot rewrites.
- Preserve citation alignment across translated/re-written claims.
- Apply safe fallbacks when translation confidence is low.
