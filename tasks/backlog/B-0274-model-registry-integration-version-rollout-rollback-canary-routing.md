# B-0274 — Model Registry 연동: Active 버전 라우팅 + Canary Rollout/Rollback

## Goal
Model Registry(DB 기반)를 기준으로 MIS/RS가 **모델 버전 라우팅**을 수행하도록 한다.

- `model_registry`의 active 모델을 조회해 기본 라우팅
- (선택) canary: 일부 트래픽만 새 모델로 라우팅
- 장애/성능 저하 시 즉시 rollback 가능한 구조

## Background
- 모델은 자주 바뀐다(학습/튜닝/최적화).
- “코드 배포”와 “모델 배포”를 분리하면 운영 난이도가 크게 내려간다.
- Admin UI(A-0125)에서 rollout/rollback을 누르면 즉시 반영되는 형태가 이상적.

## Scope
### 1) Registry contract(필수)
DB 테이블(가정):
- `model_registry(model_id, model_type, name, version, artifact_uri, status, traffic_pct, created_at, ...)`
- `eval_run(eval_id, model_id, metrics_json, passed, created_at, ...)` (Phase6 연계)

필수 조회 API(내부):
- `GET /internal/models/active?type=RERANKER`
- 응답: active version, canary version(optional), traffic pct, updated_at

### 2) Routing strategy(필수)
- 기본:
  - active 모델 100%
- canary(옵션):
  - hash 기반 분기:
    - `bucket = hash(session_id or request_id) % 100`
    - bucket < traffic_pct → canary
  - 또는 header override:
    - `x-model-version` 지정 시 강제(디버그/리플레이용)

### 3) Cache & refresh
- model config 캐시(예: 5~30초)
- 강제 refresh:
  - admin update 이벤트 수신 시 invalidate(선택)

### 4) Rollback
- canary 실패 시:
  - traffic_pct=0 또는 active를 이전 버전으로 변경
- MIS 측:
  - 로드 실패 시 즉시 “not ready” 또는 해당 모델만 제외하고 서비스 유지

### 5) Observability
- 모델별 요청 비율/latency/timeout/error
- canary vs active 비교 지표(Phase6의 online 실험과 연결 가능)

## Non-goals
- Offline eval 게이트 구현(=B-0295, I-0318)
- 실험 플랫폼 완성(A/B 프레임워크 전부)

## DoD
- RS 또는 MIS가 model_registry를 기준으로 모델 버전 선택 가능
- canary traffic_pct 설정 시 비율대로 라우팅되는지 확인
- header override로 특정 모델 고정 호출 가능
- rollback(traffic_pct 0) 시 즉시 원복 확인
- 모델별 metrics 태깅 완료

## Codex Prompt
Integrate model registry routing:
- Implement active/canary model selection based on model_registry with short TTL cache.
- Add deterministic bucketing using session_id/request_id.
- Support header override for model_version.
- Emit metrics labeled by selected model_version and canary flag, and document rollback procedure.
