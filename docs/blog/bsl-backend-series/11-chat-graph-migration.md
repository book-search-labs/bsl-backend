---
title: "11. Chat Graph Runtime: 상태 기반 대화 오케스트레이션"
slug: "bsl-backend-series-11-chat-graph-runtime"
series: "BSL Backend Technical Series"
episode: 11
status: "draft"
date: "2026-03-02"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 11. Chat Graph Runtime: 상태 기반 대화 오케스트레이션

## 문제
if/else 누적 구조는 챗 정책이 늘어날수록 회귀 분석이 어려워집니다. 그래서 노드 계약 기반 runtime으로 치환했습니다.

핵심 구현:
- `services/query-service/app/core/chat_graph/runtime.py`
- `state.py`, `confirm_fsm.py`
- `feature_router.py`, `shadow_comparator.py`
- `replay_store.py`, `canary_controller.py`

## 1) 노드 계약 고정 (`CHAT_GRAPH_NODE_CONTRACTS`)
runtime은 노드별 입력/출력 계약을 검증합니다.

실행 순서:
1. `load_state`
2. `understand`
3. `policy_decide`
4. `authz_gate`
5. `execute`
6. `compose`
7. `verify`
8. `persist`

계약 위반 시 `ChatGraphStateValidationError`로 즉시 실패합니다.

## 2) Confirm FSM
`confirm_fsm.py`는 확인 대화 흐름을 별도 FSM으로 유지합니다.

핵심 포인트:
- confirm token 검증
- idempotency 처리
- 중복 execute 차단

이 레이어가 없으면 사용자 재전송/중복 클릭에서 side effect가 쉽게 중복됩니다.

## 3) 라우팅 모드 (`feature_router.py`)
엔진 모드는 네 가지입니다.

- `legacy`
- `shadow`
- `canary`
- `agent`

플래그 입력:
- `QS_CHAT_OPENFEATURE_FLAGS_JSON`
- `QS_CHAT_FORCE_LEGACY`

또한 legacy decommission / emergency recovery 정책이 코드에 포함되어 있습니다.

## 4) shadow 비교
`shadow_comparator.py`는 legacy 결과와 graph 결과를 비교해 diff taxonomy를 남깁니다.

- `ROUTE_DIFF`
- `REASON_DIFF`
- `ACTION_DIFF`
- `CITATION_DIFF`

diff가 남으면 어떤 유형의 회귀인지 분류가 가능합니다.

## 5) canary 롤백
`canary_controller.py`는 조건 만족 시 `force_legacy` override를 적용합니다.

- 강제 롤백 키: `chat:graph:force-legacy:override`
- cooldown 동안 반복 롤백 억제

로컬에서도 실패 케이스를 replay하면서 rollback 기준을 검증할 수 있습니다.

## 6) replay 아티팩트
실행 상태 스냅샷은 `var/chat_graph/replay`에 저장됩니다. 회귀 테스트에서 같은 입력을 다시 재생하기 쉽습니다.

## 로컬 점검
```bash
curl -sS http://localhost:8001/internal/chat/session/state?session_id=test-session | jq
curl -sS http://localhost:8001/internal/rag/explain -H 'Content-Type: application/json' -d '{"query":"..."}' | jq
```

## 7) 런타임 체크포인트 저장 구조
`replay_store.py`는 run 단위 JSON 파일을 남깁니다.

1. `var/chat_graph/replay/runs/{run_id}.json`
2. node별 checkpoint와 state hash
3. request_id -> run_id index
4. replay 결과와 diff 기록

즉, 특정 요청을 동일 입력으로 재생하기 위한 증적을 남깁니다.

## 8) Confirm FSM 상태와 TTL
`confirm_fsm.py` 핵심 상태:

1. `AWAITING_CONFIRMATION`
2. `EXECUTED`
3. `EXPIRED`
4. `ABORTED`
5. `FAILED_FINAL`

관련 TTL:
- pending TTL: `QS_CHAT_GRAPH_PENDING_TTL_SEC` (기본 900)
- confirm token TTL: `QS_CHAT_CONFIRM_TOKEN_TTL_SEC` (기본 300)
- audit TTL: `QS_CHAT_GRAPH_AUDIT_TTL_SEC` (기본 86400)

## 9) 라우팅 우선순위
`feature_router.py`에서 모드 결정 우선순위는 아래입니다.

1. canary 강제 legacy override
2. force legacy flag(`QS_CHAT_FORCE_LEGACY` 또는 flags JSON)
3. langgraph enable 여부
4. engine mode (`legacy/shadow/canary/agent`)
5. high risk fallback 정책
6. legacy decommission 정책

이 순서를 이해해야 라우팅 결과를 예측할 수 있습니다.

## 10) shadow diff와 게이트 기준
`shadow_comparator.py`는 severity를 다음처럼 부여합니다.

1. `ACTION_DIFF` -> `BLOCKER`
2. `ROUTE_DIFF`/`REASON_DIFF` -> `WARN`
3. `CITATION_DIFF` -> `INFO`

gate payload에서는 blocker ratio, mismatch ratio를 계산해 PASS/WARN/BLOCK를 결정합니다.

## 11) 실전 디버깅 순서
1. routing audit에서 mode/reason 확인
2. checkpoint에서 node별 state hash 확인
3. shadow diff에서 diff type 확인
4. replay 실행 후 original/replayed mismatch 비교

이 순서를 따르면 “정책 문제 vs 구현 문제”를 분리하기 쉽습니다.
