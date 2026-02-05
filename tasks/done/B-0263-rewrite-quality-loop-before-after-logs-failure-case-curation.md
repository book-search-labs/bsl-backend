# B-0263 — QS Rewrite Quality Loop (before/after logging + failure curation)

## Goal
QS의 spell/rewrite/understanding 품질을 “운영 루프”로 개선할 수 있도록,
**전/후 비교 로그**와 **실패 케이스 큐레이션** 파이프라인을 만든다.

- rewrite/spell이 실제로 도움이 되는지(0→>0, score 개선)를 추적
- 실패 케이스를 모아서 Admin에서 재현/분석(A-0124 연계) 가능하게

## Background
- LLM/T5는 “그럴듯한” 출력을 내지만 검색 품질을 망칠 수도 있음
- 품질 개선은 반드시:
  - (1) 적용 전/후를 기록하고
  - (2) 실패를 모아
  - (3) 룰/프롬프트/모델을 수정
  - (4) 회귀 테스트로 다시 막는 사이클이 필요

## Scope
### 1) Compare log schema (DB or OLAP)
- 테이블(권장: MySQL) `query_rewrite_log` (v1)
  - `id` PK
  - `request_id`, `trace_id`, `session_id?`
  - `q_raw`, `q_norm`, `canonicalKey`
  - `reason` (ZERO_RESULTS/LOW_CONFIDENCE/HIGH_OOV)
  - `decision` (RUN/SKIP), `strategy`
  - `spell`: { q_spell, conf, method }
  - `rewrite`: { q_rewrite, conf, method }
  - `final`: { q_final, strategy }
  - `before`: { total_hits, top_score, score_gap }
  - `after`: { total_hits, top_score, score_gap }
  - `accepted`: boolean (SR이 채택했는지)
  - `failure_tag`: enum (if any)
  - timestamps

> before/after 값은 SR이 계산한 결과를 QS로 콜백하거나,
> SR이 자체적으로 `search_attempt_log`에 남기고 request_id로 조인해도 됨.
> (현실적으로는 SR 쪽 로그가 더 자연스럽고, QS는 “생성 정보” 중심으로 남겨도 됨)

### 2) Failure curation rules (v1)
자동 태깅(예시):
- `NO_IMPROVEMENT`: after.total_hits == 0 or top_score not improved
- `OVER_CORRECTION`: 편집거리 과도/토큰 변화 과도
- `ENTITY_DRIFT`: 저자/제목이 다른 엔티티로 이동(간단 휴리스틱)
- `LLM_INVALID_JSON`: 스키마 미준수
- `TIMEOUT`: stage timeout
- `COOLDOWN_SKIP`: gating으로 skip
- `LOW_CONF_OUTPUT`: conf below threshold

### 3) Export for Admin replay
- “실패 케이스 TopN”을 뽑을 수 있게 조회 API(내부)
  - `/internal/qc/rewrite/failures?from=...&limit=...`
- payload를 그대로 A-0124 Playground에 넣어 재현 가능하게

## Non-goals
- Admin UI 구현(A-0124)
- Offline eval 회귀(B-0295) (하지만 failure set의 seed로 사용)

## DoD
- rewrite/spell 실행 시 전/후 비교에 필요한 최소 로그가 남는다
- failure_tag가 자동으로 채워진다(기본 5종 이상)
- request_id로 재현 가능한 replay payload를 생성할 수 있다
- “rewrite_accept_rate”를 계산할 수 있다(지표 존재)

## Observability
- metrics:
  - qs_rewrite_attempt_total{strategy}
  - qs_rewrite_accept_total
  - qs_rewrite_failure_total{failure_tag}
- dashboards:
  - accept_rate, no_improvement_rate, timeout_rate

## Codex Prompt
Build QS rewrite quality loop:
- Create query_rewrite_log table (or equivalent) and write logs on enhance.
- Add automatic failure tagging rules.
- Provide internal API to list failure cases and export replay-ready payload.
- Add metrics for attempt/accept/failure by tag.
