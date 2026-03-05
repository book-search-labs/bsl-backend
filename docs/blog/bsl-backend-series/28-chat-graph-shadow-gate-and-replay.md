---
title: "28. Chat Graph Shadow 비교, Canary Gate, Replay 재현"
slug: "bsl-backend-series-28-chat-graph-shadow-gate-replay"
series: "BSL Backend Technical Series"
episode: 28
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 28. Chat Graph Shadow 비교, Canary Gate, Replay 재현

## 핵심 목표
Chat Graph 전환에서 중요한 것은 "맞았는지"보다 "얼마나 다르게 틀리는지"를 계량하는 것입니다.

핵심 구현 파일:
- `services/query-service/app/core/chat_graph/shadow_comparator.py`
- `services/query-service/app/core/chat_graph/canary_controller.py`
- `services/query-service/app/core/chat_graph/runtime.py`
- `services/query-service/app/core/chat_graph/replay_store.py`
- `scripts/eval/chat_graph_replay.py`

## 1) shadow diff 분류 체계
`compare_shadow_response()`는 legacy vs graph 응답을 4종 diff로 분류합니다.

- `ROUTE_DIFF`
- `REASON_DIFF`
- `ACTION_DIFF`
- `CITATION_DIFF`

## 2) 심각도 규칙
severity 결정:
- `ACTION_DIFF` 포함 -> `BLOCKER`
- `ROUTE_DIFF`/`REASON_DIFF` -> `WARN`
- `CITATION_DIFF`만 -> `INFO`

가장 위험한 차이는 사용자 행동 유도(`next_action`, `recoverable`) 불일치로 정의합니다.

## 3) diff 집계 지표
`build_shadow_summary()`는 아래를 계산합니다.

- mismatch_ratio
- blocker_ratio
- by_type, by_severity
- by_intent, by_topic

최근 window 샘플도 함께 반환해 원인 추적에 사용합니다.

## 4) canary gate 판정
`build_gate_payload()`/`evaluate_canary_gate()` 기준:

- blocker_ratio > 0.02 -> `BLOCK`
- mismatch_ratio > 0.10 -> `WARN`
- 그 외 -> `PASS`

기본 임계값은 env로 조정 가능합니다.

## 5) 자동 롤백
`apply_auto_rollback()` 동작:

1. gate 실패 시 force-legacy override 저장
2. cooldown 동안 legacy 강제
3. gate 회복 + cooldown 경과 시 override 해제

cooldown 기본값: `QS_CHAT_CANARY_COOLDOWN_SEC=600`

## 6) runtime 체크포인트 기록
`run_chat_graph(record_run=true)`이면 노드마다 `append_checkpoint()`를 호출합니다.

기록 노드:
- load_state
- understand
- policy_decide
- authz_gate
- execute
- compose
- verify
- persist

## 7) replay_store 저장 구조
저장 경로 기본값: `var/chat_graph/replay`

구성:
- `runs/<run_id>.json`
- `replays/<replay_id>.json`
- `request_index.json`

`request_id -> run_id` 인덱스로 재생 대상을 역조회할 수 있습니다.

## 8) run record 필드
`start_run_record()`는 아래를 저장합니다.

- 원본 request_payload
- replay_payload
- checkpoints
- 최종 response
- stub_response

`finish_run()`에서 status/stage/response를 완료 상태로 기록합니다.

## 9) replay diff 규칙
`response_diff()`는 아래 필드를 비교합니다.

- status, reason_code, recoverable, next_action, retry_after_ms
- answer.content
- citations 배열

결과는 `matched + mismatch 상세`로 저장됩니다.

## 10) 재현 스크립트
`scripts/eval/chat_graph_replay.py`는 `--run-id` 또는 `--request-id`로 기록을 찾아,
stub executor로 deterministic replay를 수행합니다.

출력:
- replay 레코드 JSON
- diff 결과

## 11) 로컬 실행 예시
```bash
python scripts/eval/chat_graph_replay.py \
  --request-id req_xxx \
  --output-json var/chat_graph/replay/replay_result.json
```

확인 포인트:
1. `status=ok|mismatch`
2. `diff.mismatch` 항목
3. gate 지표에 반영되는 diff type

## 12) 구현상 의도
Shadow/Replay는 "문제 발생 후 디버깅" 도구가 아니라, 전환 전 품질 검증 장치입니다.

즉, canary 전환의 기준을 감각이 아니라 수치로 고정하는 것이 핵심입니다.
