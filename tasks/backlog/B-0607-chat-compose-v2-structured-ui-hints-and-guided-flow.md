# B-0607 — Chat Compose v2 (Structured UI Hints + Guided Flow)

## Priority
- P1

## Dependencies
- B-0602
- B-0603
- B-0606

## Goal
자연어 응답을 선택형 인터랙션 구조로 확장해 검색/추천/액션 완료율을 높인다.

## Why
- 인터랙션 챗봇은 문장 품질보다 `카드/옵션/버튼` 구조가 체감 품질을 좌우함

## Scope
### 1) Structured response
- `ui_hints.options` (quick replies)
- `ui_hints.cards` (book top3)
- `ui_hints.forms` (slot input)
- `ui_hints.buttons` (confirm/cancel)

### 2) Route-aware rendering
- `OPTIONS` route 시 후보 카드 + 선택 버튼 강제
- `CONFIRM` route 시 요약 + 확인/취소 버튼 강제

### 3) Channel fallback
- 카드 미지원 채널에서는 text fallback 자동 생성

## DoD
- 검색/추천 경로에서 카드 기반 선택 UX가 기본 제공된다.
- confirm 경로에서 표준 버튼 인터랙션을 제공한다.
- 채널별 fallback 렌더가 깨지지 않는다.

## Interfaces
- chat response schema (`ui_hints`)
- web/app renderer contract

## Observability
- `chat_ui_hints_render_total{type}`
- `chat_option_select_total{source}`

## Test / Validation
- schema compatibility tests
- route-to-ui mapping tests
- multi-channel rendering snapshots

## Codex Prompt
Upgrade response composer with structured interaction hints:
- Emit options/cards/forms/buttons by route.
- Enforce guided selection and confirmation patterns.
- Provide safe text fallback for unsupported channels.
