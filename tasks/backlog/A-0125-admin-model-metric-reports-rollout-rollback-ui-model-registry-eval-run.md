# A-0125 — Admin Model Registry & Metrics Report UI (rollout/rollback)

## Goal
검색/랭킹/챗봇 모델 운영을 위한 **모델 레지스트리 + 평가 지표 + 롤아웃/롤백 UI** 제공.
- model_registry 등록 모델 조회
- eval_run(offline eval) 결과 리포트
- canary → rollout → rollback 작업 트리거(정책 기반)

## Background
- LTR/MIS/cross-encoder는 “모델 버전 운영”이 핵심.
- offline eval 회귀 게이트가 있어도, 운영자가 결과를 보고 배포/롤백할 UI가 필요하다.

## Scope
### 1) Model Registry List/Detail
- 모델 타입: LTR / RERANKER / EMBEDDING / RAG (확장)
- 필드:
  - name, version, status(active/candidate/deprecated)
  - artifact_uri, created_at
  - runtime_requirements(cpu/gpu), max_batch, max_len(옵션)
- detail: metadata_json 표시

### 2) Eval Report
- eval_run list (모델버전별)
- metrics:
  - ndcg@10, mrr@10, recall@100, zero_result_rate, latency_proxy
- 비교:
  - baseline 대비 delta 표시
  - gate pass/fail 표시

### 3) Rollout / Rollback
- canary 시작(예: 5%)
- 점진 rollout(5→25→50→100)
- 즉시 rollback(이전 active)
- 정책/버킷 기반 라우팅(실험 연동은 선택)

## Non-goals
- eval runner 구현(B-0295)
- MIS 라우팅 구현(B-0274)

## Data / API (via BFF)
- `GET /admin/models`
- `GET /admin/models/{model_id}`
- `GET /admin/models/{model_id}/eval-runs`
- `POST /admin/models/{model_id}/rollout` (payload: strategy/canary_pct)
- `POST /admin/models/{model_id}/rollback`

## Persistence (assumed existing)
- model_registry, eval_run 테이블 사용(이미 설계된 스키마 기준)

## Security / Audit
- rollout/rollback은 RBAC 강제 + audit_log 기록
- “위험 작업 2인 승인”(옵션) 확장 가능

## DoD
- 운영자가 모델 버전과 성능 변화(델타)를 한 눈에 확인
- canary/rollout/rollback 트리거 가능
- 감사로그/권한 정책 적용 완료

## Codex Prompt
Admin(React)에서 Model Registry/Eval Report/Rollout UI를 구현하라.
모델 목록/상세, eval metrics 비교, canary/rollout/rollback 액션을 제공하라.
BFF API 경유 + RBAC + audit_log 전제를 적용하라.
