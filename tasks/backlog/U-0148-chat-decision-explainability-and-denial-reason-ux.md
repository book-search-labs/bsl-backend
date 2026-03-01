# U-0148 — Chat Decision Explainability + Denial Reason UX

## Priority
- P2

## Dependencies
- B-0383, B-0371, U-0144

## Goal
챗봇이 왜 해당 답변/거절/추가질문을 했는지 사용자에게 이해 가능한 방식으로 설명해 신뢰를 높인다.

## Scope
### 1) Decision reason cards
- "왜 이 답변인가", "왜 실행이 제한됐는가" 요약 카드 제공
- reason_code 기반 한국어 설명 문구 매핑

### 2) Denial guidance UX
- 거절 시 가능한 대체경로(추가정보, 티켓, 상담전환) 제시
- 사용자 행동 유도 버튼 제공

### 3) Citation + policy transparency
- 출처/정책 기준일/적용 정책 버전 링크 제공
- 민감 액션 제한 사유를 최소한의 범위에서 공개

### 4) Accessibility
- 모바일 카드 레이아웃/스크린리더/대비 기준 준수

## DoD
- 거절/제한 응답에 대한 사용자 혼란 감소
- 대체경로 전환율 개선
- reason_code 기반 UX 일관성 확보

## Codex Prompt
Improve explainability UX for chat decisions:
- Show user-friendly reason cards for answers, denials, and clarifications.
- Provide actionable alternatives after denied actions.
- Surface policy/citation context in concise Korean UX patterns.
