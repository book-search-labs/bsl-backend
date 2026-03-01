# U-0154 — Chat Resolve Center + Human Handoff UX

## Priority
- P1

## Dependencies
- U-0152, U-0153
- B-0395, A-0151

## Goal
사용자가 책봇에서 문제를 끝까지 해결할 수 있도록 "해결 센터" UX와 상담원 전환 UX를 표준화한다.

## Scope
### 1) Resolve center panel
- 챗 위젯 내부에 진행 단계, 확정 정보, 남은 입력값을 카드로 표시
- 액션별 예상 결과(환불 금액/배송비/처리 시간) 요약 카드 노출
- 카드 클릭 시 해당 단계 재열기(수정/재시도)

### 2) Human handoff UX
- 자동 해결 실패/고위험 상태에서 상담 전환 CTA 우선 노출
- 전환 시 대화 요약, 근거, 실행 이력 자동 첨부
- 예상 대기 시간 및 접수 상태를 사용자에게 표시

### 3) Error and recovery UX
- `next_action` 기반 복구 버튼(재시도/입력수정/상담전환) 표준 배치
- 네트워크 끊김/타임아웃 시 세션 복구 토스트 + 자동 재연결
- 모바일/데스크톱 공통 접근성(포커스/스크린리더/터치 타깃) 보장

## DoD
- 해결 센터 진입 후 문의 완료율이 기존 대비 상승
- 상담 전환 시 누락 정보 없이 접수가 자동 생성됨
- 실패 케이스에서 사용자 이탈률 감소가 지표로 확인됨

## Codex Prompt
Upgrade chat UX with a resolve center:
- Show progress, confirmed facts, and expected outcomes in actionable cards.
- Add robust human handoff flow with summarized context and wait-time visibility.
- Standardize recovery actions for timeout/network/policy failures.
