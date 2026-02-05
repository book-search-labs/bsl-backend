# B-0252 — Ranking Service Debug Mode (Explain + Replay-ready)

## Goal
Ranking Service(RS)가 “왜 이 순서가 나왔는지”를 운영/디버깅할 수 있도록 **디버그 모드(explain)**를 제공한다.

- 요청마다 **model_version / feature_set_version / 사용 피처 / 스코어 breakdown** 반환
- 실서비스 응답에는 기본적으로 숨기고, `debug=true` 또는 내부 엔드포인트에서만 활성화
- Admin Playground(A-0124)에서 “쿼리/후보 재생(replay)”을 가능하게 만드는 기반

## Background
- LTR/리랭킹 운영에서 가장 자주 터지는 이슈:
  - 특정 쿼리에서 갑자기 이상한 결과(품질 regression)
  - 피처 누락/기본값 fallback이 과도
  - 특정 모델 버전이 문제
- 디버그 모드 없으면 “감으로”만 수정하게 되고, 결국 망한다.

## Scope
### 1) API surface (internal)
- POST `/internal/rank`
  - request: { request_id, query_context, candidates[], policy, debug? }
  - response: { ranked[], debug? }

### 2) Debug payload (when debug=true)
- request-level
  - `model`: { type, name, version, artifact_id }
  - `feature_set_version`
  - `policy`: { rerank_strategy, topN, topK, timeouts }
  - `latency_ms`: { feature_fetch, model_infer, total }
  - `fallback_used`: boolean + reason
- item-level (topK 혹은 topR까지만)
  - `doc_id`
  - `scores`: { base_score?, ltr_score?, ce_score? }
  - `features_used`: { f1: v, f2: v, ... }  (필요 시 whitelist)
  - `missing_features`: [..]
  - `reason_codes`: [ "FEATURE_FALLBACK", "MODEL_TIMEOUT", ... ]

> 개인정보/민감정보는 절대 포함하지 않는다.

### 3) Debug output size controls
- debug는 상한을 둔다:
  - `debug_max_items` (예: 50)
  - `debug_max_features` (예: 30)
  - 기본은 요약만, 상세는 옵션 필드로

### 4) Replay readiness
- 동일 요청을 재현 가능하게:
  - request hash
  - candidate snapshot hash
  - spec_version 기록
- (연계) Admin에서 "replay" 버튼으로 같은 payload 재전송 가능

## Non-goals
- 모델 학습/평가 파이프라인(B-0294/0295)
- Admin UI 구현(A-0124) 자체

## DoD
- debug 플래그로 debug payload on/off
- model/spec/policy/version이 debug에 포함
- item-level breakdown 제공(상한 적용)
- debug 모드에서도 타임아웃/서킷브레이커 정책 동일 적용
- 샘플 replay payload를 docs에 제공

## Observability
- metrics:
  - rs_debug_requests_total
  - rs_debug_payload_bytes (histogram)
  - rs_missing_features_total{feature}
- logs:
  - request_id, model_version, spec_version, fallback_reason

## Codex Prompt
Implement RS debug mode:
- Extend rank response with debug block when debug=true.
- Include model/spec/policy versions, per-stage latency, fallback flags.
- Include per-item score breakdown + missing features (bounded).
- Add payload size guards and docs with a replay example JSON.
