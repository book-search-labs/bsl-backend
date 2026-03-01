# U-0149 — Chat Risk-state Visualization + User-safe Flow UX

## Priority
- P2

## Dependencies
- B-0390, U-0148, U-0147

## Goal
사용자가 챗봇 응답의 위험상태(일반/주의/제한)를 UI에서 즉시 파악하고 안전한 다음 행동을 선택하도록 돕는다.

## Scope
### 1) Risk state badges
- 답변 카드에 위험상태 배지(`일반/주의/제한`) 표시
- 상태별 시각적 구분 및 툴팁 안내

### 2) Safe flow actions
- 제한 상태에서 실행 대신 대체경로(추가정보/티켓/상담) 제시
- 주의 상태에서 확인 질문 CTA 제공

### 3) Context retention UX
- 위험상태 전환 이력 타임라인 표시
- 사용자가 이전 안전답변으로 복귀 가능

### 4) Accessibility/mobile
- 색상 의존 최소화, 텍스트 레이블 병행
- 모바일 레이아웃 최적화

## DoD
- 위험응답에서 사용자 오해/오조작 감소
- 안전 대체경로 전환율 개선
- 위험상태 UI 일관성 확보

## Codex Prompt
Design UX for risk-aware chat responses:
- Visualize answer risk states with clear badges and explanations.
- Guide users to safe alternatives when execution is restricted.
- Keep the flow accessible and mobile-friendly in Korean.
