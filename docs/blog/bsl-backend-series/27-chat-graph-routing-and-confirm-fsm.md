---
title: "27. Chat Graph 라우팅 + Confirm FSM: 실행 전 통제 계층"
slug: "bsl-backend-series-27-chat-graph-routing-confirm-fsm"
series: "BSL Backend Technical Series"
episode: 27
status: "draft"
date: "2026-03-03"
last_modified: "2026-03-03"
tags:
  - bsl
  - backend
  - technical-blog
---

# 27. Chat Graph 라우팅 + Confirm FSM: 실행 전 통제 계층

## 핵심 목표
Chat Graph는 LLM 품질과 별개로, "어떤 엔진으로 처리할지"와 "민감 작업을 실행해도 되는지"를 먼저 결정합니다.

핵심 구현 파일:
- `services/query-service/app/core/chat_graph/feature_router.py`
- `services/query-service/app/core/chat_graph/confirm_fsm.py`
- `services/query-service/app/core/chat.py`

## 1) 엔진 모드 결정 우선순위
`resolve_engine_mode()`는 아래 순서로 판단합니다.

1. canary 강제 롤백 override
2. force legacy 플래그(env/openfeature)
3. langgraph 활성 플래그
4. mode 플래그(`legacy|shadow|canary|agent`)
5. 고위험 정책 fallback
6. legacy decommission 정책

즉, 단순 mode 값 하나로 결정하지 않습니다.

## 2) 플래그 입력 소스
라우터는 `QS_CHAT_OPENFEATURE_FLAGS_JSON`과 env를 함께 사용합니다.

지원 오버라이드 축:
- defaults
- tenants
- users

동일 key여도 사용자/테넌트 설정이 우선됩니다.

## 3) force-legacy와 decommission의 동시 처리
- `chat.force_legacy=true`면 무조건 legacy
- 반대로 `legacy_decommission_enabled=true`면 legacy를 agent로 밀어냅니다.
- 단, `legacy_emergency_recovery=true`면 다시 legacy 허용

이 조합으로 점진 전환과 긴급 복귀를 모두 지원합니다.

## 4) 라우팅 감사 로그
`append_routing_audit()`는 세션별 + 글로벌 로그를 캐시에 남깁니다.

기록 필드:
- mode, reason, source
- force_legacy
- trace/request/session/context

TTL은 86400초, 세션 최대 200건, 글로벌 최대 1000건입니다.

## 5) Confirm FSM의 상태
`confirm_fsm.py`의 터미널 상태:
- `EXECUTED`
- `EXPIRED`
- `ABORTED`
- `FAILED_FINAL`

터미널 상태 재요청은 `CONFIRMATION_REPLAYED`로 차단됩니다.

## 6) pending action 생성
`init_pending_action()`은 아래를 저장합니다.

- `state=AWAITING_CONFIRMATION`
- `confirmation_token` (6자리)
- `idempotency_key`
- `expires_at`
- `risk_level=HIGH`

이후 audit trail을 남깁니다.

## 7) 확인 메시지 판정
`evaluate_confirmation()` 분기:

1. 만료 -> `CONFIRMATION_EXPIRED`
2. 중단 의사 -> `USER_ABORTED`
3. 확인 의사 없음 -> `CONFIRMATION_REQUIRED`
4. 코드 불일치 -> `CONFIRMATION_TOKEN_MISMATCH`
5. 코드 일치 -> `CONFIRMED` + 실행 허용

## 8) TTL 관련 설정
기본 TTL:
- `QS_CHAT_GRAPH_PENDING_TTL_SEC=900`
- `QS_CHAT_CONFIRM_TOKEN_TTL_SEC=300`
- `QS_CHAT_GRAPH_AUDIT_TTL_SEC=86400`

토큰 TTL이 지나면 pending이 남아 있어도 만료 처리됩니다.

## 9) 실행 단계 연계
확인 완료 후 runtime에서
- `mark_execution_start()` -> `EXECUTING`
- `mark_execution_result()` -> `EXECUTED` 또는 실패 상태

상태 전이마다 audit 이벤트가 추가됩니다.

## 10) chat.py에서의 연결
`run_chat()`는 mode에 따라
- `legacy`
- `shadow` (legacy 응답 반환 + graph 비교)
- `canary/agent` (graph 응답 반환)

으로 분기하며, 라우팅 감사 기록을 남깁니다.

## 11) 로컬 점검
1. `QS_CHAT_ENGINE_MODE=agent`로 실행
2. 민감 질의 입력
3. 응답의 `next_action=CONFIRM_ACTION` 확인
4. `확인 <코드>` 입력 후 실행 응답 확인

## 12) 구현상 의도
이 FSM의 목적은 "추가 UX"가 아니라 "실수 실행 방지"입니다.

특히 사이드프로젝트 환경에서는 사람 검수 단계가 없으므로, 런타임에서 확인 상태를 명시적으로 강제하는 것이 안전성의 핵심입니다.
