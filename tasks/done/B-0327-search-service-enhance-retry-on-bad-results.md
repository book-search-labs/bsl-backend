# B-0232 — Search Service: “나쁜 결과”일 때만 QS /query/enhance로 1회 재검색(2-pass)

## Goal
- SR이 첫 검색이 “나쁘다”고 판단되면:
  1) QS `/query/enhance` 호출(spell/rewrite)
  2) **최대 1회** 재검색
- debug에 enhanceApplied/reason/finalQuery를 남긴다.

## Why
- Architecture v3 fallback: **0 results/low confidence → QS enhance → retry once**

## Scope
### In scope
- SR에 `SearchQualityEvaluator` 추가(사유 코드 산출)
- 조건 만족 시 QS enhance 호출 + retry once
- retry 시 query text만 교체(필터/옵션 유지)
- 재시도는 딱 1회(재귀/루프 금지)

### Out of scope
- multi-retry(2회 이상)
- LLM 기반 understanding

## MVP Quality Rules(초기)
- ZERO_RESULTS: hits == 0
- LOW_RESULTS: hits < 3 AND topScore < threshold (서비스 상황에 맞게)
- (옵션) LOW_CONFIDENCE: score 분포가 너무 평평함

## SR → QS /query/enhance 요청 예시
```json
{
  "trace_id": "trace_xxx",
  "request_id": "req_xxx",
  "q_norm": "정규화쿼리",
  "q_nospace": "공백제거",
  "reason": "ZERO_RESULTS",
  "signals": { "hits": 0, "top_score": 0.0, "from": 0, "size": 10 },
  "locale": "ko-KR",
  "debug": false
}
```

## Deliverables
	•	SR 내부 QS client 추가
	•	HybridSearchService(or orchestrator)에 “retry once” 추가
	•	debug 응답 확장(가능하면)

## Acceptance Criteria
	•	hits==0이면 enhance 호출 후 재검색 수행
	•	재검색은 최대 1회
	•	enhance가 SKIP이면 재검색 없이 1-pass 결과 반환
	•	timeout budget/CB로 p99 보호

## Test plan
	•	evaluator 단위 테스트(사유 코드)
	•	통합 테스트: 0-result 쿼리 → enhance → retry 확인

