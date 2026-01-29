# B-0262 — QS 2-pass Gating (cost governor) for spell/rewrite/RAG

## Goal
QS의 expensive 단계(2-pass: spell/rewrite/(optional)RAG)를 **운영형 비용/지연 예산** 안에서만 실행되도록 “게이팅(cost governor)”을 구현한다.

- 2-pass는 **항상 실행 금지**
- 트리거 조건 + 예산 + 쿨다운 + 상한을 통해 **p99/비용 폭발 방지**
- 최종 채택은 SR이 “전/후 비교”로 결정 가능(안전장치)

## Background
- LLM/T5/RAG 호출은 지연과 비용을 급격히 올림
- “0건/애매함”에서만 호출해야 운영이 된다
- 또한 동일 쿼리에 반복적으로 2-pass가 걸리면 비용이 누적됨 → 쿨다운 필요

## Scope
### 1) 2-pass 엔드포인트/입력
- POST `/query/enhance`
  - input:
    - `request_id`, `trace_id`
    - `q_norm`, `q_nospace`, `detected`
    - `reason` (from SR): `ZERO_RESULTS` | `LOW_CONFIDENCE` | `HIGH_OOV` | `USER_EXPLICIT`(옵션)
    - `signals`:
      - `top_score`, `score_gap`, `oov_ratio`, `token_count`, `latency_budget_ms`
    - `top_candidates`(optional): SR이 준 상위 후보 일부(title/author/snippet)

### 2) Gating 정책(룰/스코어)
- rule-based v1 (빠르게/명확하게)
  - trigger:
    - `reason == ZERO_RESULTS`
    - `reason == HIGH_OOV`
    - `reason == LOW_CONFIDENCE && score_gap < threshold`
    - `detected.mode == chosung` -> rewrite 우선(선택)
    - `detected.is_isbn == true` -> 2-pass skip(ISBN search로 분기)
  - deny:
    - request budget exhausted
    - cooldown hit
    - repeated identical query too frequently
    - latency_budget_ms too low
- 출력:
  - `decision`: RUN | SKIP
  - `strategy`: SPELL_ONLY | REWRITE_ONLY | SPELL_THEN_REWRITE | RAG_REWRITE (optional)
  - `reason_codes`: [..]

### 3) Budget & cooldown (필수)
- per-query cooldown:
  - key = `canonicalKey` (from B-0261) or hash(q_norm+locale)
  - store in Redis:
    - last_enhance_at
    - enhance_count_window
- global budget:
  - per-minute / per-5min max enhance calls
  - (옵션) token budget / cost budget (LLM Gateway와 연동 가능)
- parameters (env/config):
  - `qs_enhance_max_rps`, `qs_enhance_window`, `qs_enhance_cooldown_sec`
  - `qs_enhance_max_per_query_per_hour`

### 4) Execution plan (when RUN)
- 단계별 타임아웃 예산 고정:
  - spell: 80ms
  - rewrite/understanding: 250~800ms (상용 LLM이면)
  - total enhance: 900ms (예시)
- 실패 시 degrade:
  - spell 실패 → rewrite만 시도(정책)
  - rewrite 실패 → q_norm 반환 + fail reason

## Non-goals
- T5 spell 모델 자체 구현(별도 티켓으로 분리 가능)
- LLM Gateway(B-0283) 구현 (단, 인터페이스는 맞춘다)

## DoD
- enhance 호출이 gating decision을 통과해야만 실행됨
- cooldown/상한이 Redis에 의해 강제됨
- decision/strategy/reason_codes가 응답에 포함됨
- SR에서 제공한 reason/signals로 재현 가능
- metrics/logs로 enhance rate/skip rate 관측 가능

## Observability
- metrics:
  - qs_enhance_requests_total{decision,strategy,reason}
  - qs_enhance_skipped_total{skip_reason}
  - qs_enhance_latency_ms{stage}
  - qs_enhance_cooldown_hits_total
- logs:
  - request_id, canonicalKey, decision, strategy, reason_codes

## Codex Prompt
Implement QS enhance gating:
- Add /query/enhance endpoint that takes reason+signals from SR.
- Compute decision (RUN/SKIP) and strategy based on rules + budgets.
- Enforce per-query cooldown + global limits using Redis.
- Return decision/strategy/reason_codes and emit metrics/logs.
