# B-0273 — SR/RS Fallback 정책(운영 안전): MIS 장애/지연 시 Degrade로 SLA 유지

## Goal
MIS(모델 추론) 또는 RS(리랭킹) 의존성이 **느리거나 장애**일 때도,
Search 결과를 “0건/오류”로 만들지 않고 **항상 Degraded 결과라도 반환**하도록
SR/RS의 **Fallback/Degrade 정책을 표준화**한다.

- MIS timeout/5xx → RS는 “점수 없음”으로 처리
- RS 실패 → SR은 **(1) Fusion 순서** 또는 **(2) BM25-only**로 즉시 복귀
- 품질 저하 여부를 응답에 명시(`pipeline.degraded=true`, reason)

## Background
- 운영에서 가장 큰 문제는 **연쇄 장애**:
  - MIS가 느려짐 → RS 대기 → SR 대기 → 전체 검색 타임아웃
- 품질(precision)보다 SLA(응답 제공)가 우선인 상황이 많다.
- Degrade를 명시적으로 설계해야 “장애 시나리오”가 예측 가능해진다.

## Scope
### 1) Budget & Timeout 표준(필수)
- SR 전체 예산 예시(환경별 조정):
  - BM25 retrieval: 80~150ms
  - Vector retrieval: 120~250ms (optional)
  - RS rerank call: 80~200ms
  - Total p99 target: 600~900ms (MVP)
- RS→MIS timeout:
  - hard timeout (예: 200ms)
  - connect timeout (예: 50ms)

### 2) Degrade 단계(필수)
**Stage A: Rerank degrade**
- 조건:
  - MIS timeout/5xx/queue reject(429/503)
- 동작:
  - RS는 rerank 생략하고 “원래 후보 순서” 반환 + degraded flag
  - SR은 fusion 결과 또는 bm25 결과 그대로 응답

**Stage B: Vector degrade**
- 조건:
  - embedding 경로 실패 / knn 느림 / OS partial failure
- 동작:
  - hybrid 모드라도 vector를 끄고 BM25-only로 응답

**Stage C: Total fail-safe**
- 조건:
  - OpenSearch 오류/timeout, 일부 shard 실패
- 동작:
  - “부분 결과라도” 반환(가능하면)
  - 불가하면 빈 결과 대신 “friendly empty + retryable error meta” (정책 선택)

### 3) Circuit Breaker / Hedging(권장)
- SR:
  - MIS/RS에 circuit breaker 적용(연속 실패 시 일정 시간 차단)
  - hedged request(선택): p99 튐 방지(주의: 비용 증가)
- RS:
  - MIS 호출을 bulkhead(동시성 제한)로 격리

### 4) Response/Logging 표준(필수)
- SR 응답 `pipeline` 필드:
  - `pipeline.rerank_used` (bool)
  - `pipeline.vector_used` (bool)
  - `pipeline.degraded` (bool)
  - `pipeline.degrade_reason` (enum)
  - `pipeline.timeouts` (stage별)
- 로그/메트릭:
  - degrade rate(유형별)
  - timeout rate
  - circuit open 비율

## Non-goals
- 품질 최적화 자체(=B-0266, B-0294 등)
- canary routing(=B-0274)

## DoD
- SR/RS에 degrade 정책이 코드/문서로 고정됨
- MIS 장애/지연을 강제로 발생시키는 테스트 시나리오에서:
  - SR은 200/정상 JSON 응답 유지
  - `pipeline.degraded=true` 및 reason 포함
- 메트릭/대시보드용 지표가 노출됨

## Degrade Reason Enum (예시)
- `MIS_TIMEOUT`
- `MIS_REJECTED`
- `MIS_5XX`
- `VECTOR_TIMEOUT`
- `OS_PARTIAL_FAILURE`
- `RS_TIMEOUT`
- `UNKNOWN`

## Codex Prompt
Implement SR/RS degrade policy:
- Add strict timeouts and circuit breakers for RS→MIS and SR→RS.
- If MIS fails, return non-reranked results with pipeline.degraded flags.
- If vector/hybrid fails, fallback to BM25-only.
- Add metrics for degrade reasons and timeout rates, and include pipeline metadata in responses.
