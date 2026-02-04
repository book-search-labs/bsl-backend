# B-0239 — Observability: enhance 트리거/재시도 결과/검색 품질 메트릭

## Goal
- 2-pass enhance가 언제/왜/효과 있었는지 관측 가능하게 만든다.

## Scope
### In scope
SR metrics:
- sr_enhance_attempt_total{reason=...}
- sr_enhance_success_total{improved=true/false}
- sr_enhance_latency_ms
- sr_search_retry_total

Logging:
- request_id, trace_id, reason, strategy, final_source, improved

Improved(MVP):
- hits 증가 OR top1 score 증가 OR 0→>0

## Acceptance Criteria
- [ ] enhance 시도가 메트릭으로 보임
- [ ] improved 여부 기록됨
- [ ] budget 부족/timeout도 reason code로 남음
