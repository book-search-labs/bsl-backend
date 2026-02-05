# B-0260 — QueryContext v1 Contract + Trace Propagation (E2E)

## Goal
QS(Query Service)가 출력하는 **QueryContext v1**을 계약(Contract)으로 고정하고,
BFF→QS→SR→RS/MIS 전 구간에서 **request_id/trace_id**가 일관되게 전파되도록 한다.

- QueryContext는 “검색 파이프라인 공용 입력 포맷”
- trace propagation은 “관측/디버그/성능 개선”의 전제 조건

## Background
- QueryContext가 흔들리면 SR/RS 구현이 계속 깨지고 실험도 불가능.
- trace_id가 없으면 “어디가 느린지/왜 degrade됐는지”를 못 찾는다.

## Scope
### 1) QueryContext v1 schema (minimal but sufficient)
필수 필드:
- `request_id`, `trace_id`, `span_id?`
- `q_raw`, `q_nfkc`, `q_norm`, `q_nospace`
- `locale`, `client` (web/admin/mobile)
- `detected`:
  - `mode`: normal | chosung | isbn | mixed
  - `is_isbn`, `has_volume`, `lang`
- `hints`:
  - `intent_hint?` (검색/상품/저자/시리즈)
  - `budget?` (low_latency_mode 등)
- `confidence`:
  - `need_spell`, `need_rewrite`, `need_rerank` (0..1)
- `expanded` (optional):
  - aliases/series/author_variants

### 2) Contract storage
- `contracts/query_context/v1/*.json` (JSON Schema)
- OpenAPI에 QS endpoint request/response로 포함

### 3) Trace propagation rules
- incoming:
  - BFF가 `x-request-id`, `traceparent` 생성/전달
- QS:
  - header로 받은 trace를 그대로 사용 + 로그에 포함
  - 내부 호출(캐시/모델)도 span 생성
- QS response:
  - QueryContext에 request_id/trace_id를 echo
- SR/RS/MIS:
  - 동일 헤더 규칙 준수

### 4) CI checks
- Contract breaking change 감지 (B-0226 연계)
- 샘플 payload fixtures로 schema validation 테스트

## Non-goals
- QS 내부 normalize/detect 알고리즘(B-0261)
- OTel 인프라 구성(I-0302)

## DoD
- QueryContext v1 JSON Schema 확정 + repo에 고정
- QS `/query/prepare`가 v1을 준수
- BFF→QS→SR까지 request_id/trace_id가 logs에서 연계됨
- contract 테스트가 CI에서 통과/실패를 결정

## Observability
- QS metrics:
  - qs_prepare_latency_ms
  - qs_schema_validation_fail_total
- logs:
  - request_id, trace_id, q_hash, detected.mode

## Codex Prompt
Define QueryContext v1:
- Add JSON Schema + fixtures and integrate into OpenAPI.
- Update QS prepare endpoint to output QueryContext v1.
- Implement trace propagation via x-request-id + traceparent and ensure logs include them.
- Add CI test that validates fixtures and rejects breaking changes.
