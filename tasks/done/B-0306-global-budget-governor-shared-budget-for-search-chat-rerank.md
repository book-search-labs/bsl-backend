# B-0306 — Global budget governor(검색/챗/리랭킹 공통 예산제)

## Goal
QS/SR/MIS/LLM 호출을 “쿼리별/요청별 예산(budget)”으로 통제해서
- 비용 폭주를 막고
- p99 지연을 보호하며
- 장애 시 자동 degrade가 되게 만든다.

## Why
- 2-pass(LLM/T5), hybrid embedding, rerank(MIS), RAG generation은 모두 “비싼 단계”
- 트래픽이 늘면 비용/지연이 선형 이상으로 폭발할 수 있음 → 예산제가 운영 필수

## Scope
### 1) Budget Model 정의
요청 단위 Budget:
- `max_total_ms`
- stage별 `max_stage_ms`:
  - qs_prepare, qs_enhance, bm25, embedding, knn, fusion, rerank, generate
- stage별 `max_calls`:
  - rerank_topR cap, 2-pass 호출 cap, retrieve topN cap
- 비용 예산(옵션):
  - `max_llm_tokens`, `max_llm_cost_usd`

### 2) Budget 결정 로직
입력 신호:
- request mode(search/chat)
- user tier(익명/로그인/관리자)
- experiment bucket
- system health(서킷브레이커 상태, p99 상승 여부)

결정:
- policy 기반 기본값 + 런타임 조정(“health-based”)

### 3) 적용 지점
- BFF:
  - request 시작 시 budget을 계산해 downstream에 전달(header 또는 body)
- QS:
  - 2-pass gate(B-0262)를 budget과 통합
- SR:
  - topN/topR, embedding/knn 호출 여부를 budget 기반으로 결정
- MIS/LLM Gateway:
  - concurrency/queue/timeouts/token cap enforcement

### 4) Degrade Policy (필수)
예산 초과/의존 실패 시 단계적 축소:
- rerank 실패 → fused 순서로 응답
- vector 실패 → bm25-only
- qs_enhance 실패 → 1-pass만
- chat generate 실패 → “출처 기반 검색 결과 + 요약 불가” fallback

### 5) Observability
- budget applied config 로그
- stage별 “budget exceeded” 카운터
- degrade rate, llm_call_rate, rerank_call_rate
- 비용 추정(토큰/호출수 기반) 대시보드

## Non-goals
- 완벽한 비용 청구 시스템
- 실시간 과금/결제 연동

## DoD
- budget 스키마가 정의되고 BFF→QS/SR/MIS/LLM에 전파된다
- 예산 초과/장애 시 degrade가 자동으로 동작한다(0건/타임아웃 방지)
- 메트릭으로 호출율/감소율/지연 영향이 관측된다
- 핫 트래픽 상황에서 비용 폭주가 제어된다

## Codex Prompt
Implement global budget governor:
- Define a budget schema (time, calls, token/cost caps) and propagate it from BFF to QS/SR/MIS/LLM gateway.
- Enforce budget at each stage: 2-pass gating, retrieval topN/topR caps, embedding/knn toggles, rerank/generate limits.
- Add degrade policies for partial failures and budget overruns and expose metrics for exceed/degrade rates.
- Provide minimal integration tests demonstrating degrade behavior under forced timeouts.
