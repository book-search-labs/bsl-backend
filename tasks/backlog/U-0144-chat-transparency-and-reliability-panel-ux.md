# U-0144 — Chat Transparency & Reliability Panel UX

## Priority
- P2

## Dependencies
- B-0363, B-0368, I-0353

## Goal
사용자가 챗봇 답변의 신뢰 상태(근거 신뢰도/최신성/오류복구 상태)를 UI에서 즉시 이해할 수 있게 한다.

## Scope
### 1) Reliability panel
- 답변별 reliability level, freshness, source type 배지 표시
- fallback/degrade 응답 시 원인 및 재시도 버튼 제공

### 2) Session health hint
- 세션 복구 여부/중단 이력/미완료 workflow 상태 안내
- 필요시 "이어서 진행" 액션 제공

### 3) Safe action UX
- 민감 액션 실행 전 확인 단계 시각화
- 확인/취소/상담 전환을 명확히 분리

### 4) Accessibility/mobile
- 모바일 가독성, 스크린리더 라벨, 색상 대비 기준 충족

## DoD
- 사용자 신뢰도 관련 이탈률/반복질문율 개선
- fallback 상황 재시도 성공률 개선
- 접근성 체크리스트 통과

## Codex Prompt
Improve chat trust UX:
- Add a reliability panel with source/freshness/recovery indicators.
- Make fallback causes and retry actions explicit.
- Visualize sensitive-action confirmation clearly on desktop/mobile.
