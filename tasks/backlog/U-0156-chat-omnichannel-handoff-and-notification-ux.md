# U-0156 — Chat Omnichannel Handoff + Notification UX

## Priority
- P1

## Dependencies
- U-0154, U-0155
- B-0397

## Goal
책봇 상담이 중단되거나 상담원으로 전환될 때 사용자에게 채널을 넘어 일관된 진행 상태와 알림 경험을 제공한다.

## Scope
### 1) Omnichannel handoff UX
- 웹 챗 -> 주문/고객센터 화면 전환 시 진행 상태 배지 유지
- 상담 이관 시 접수번호/예상 응답 시간/현재 단계 표시
- 이관 후 챗 위젯에서 동일 케이스 진행 현황 조회 가능

### 2) Notification center
- 상태 변경(접수/처리중/완료/추가입력요청) 인앱 알림 제공
- 알림 클릭 시 해당 케이스/대화 단계로 딥링크 이동
- 읽음/미읽음, 중요도 구분 UI 제공

### 3) Re-open and continue
- 처리 완료 후 재문의(케이스 재열기) UX 제공
- 최근 해결 케이스 요약과 "같은 문제 다시 문의" CTA 제공
- 모바일 푸시 연계 확장용 UI slot 정의

### 4) Accessibility and consistency
- 알림/배지/상태칩 컴포넌트 디자인 시스템화
- 저시력/스크린리더 대응 라벨과 포커스 순서 보장

## DoD
- 이관 이후 사용자 상태 혼선(현재 진행 단계 미인지) 지표 감소
- 알림 클릭 기반 재진입률/해결률이 개선됨
- 모바일/데스크톱에서 동일한 상태 모델로 동작함

## Codex Prompt
Build omnichannel handoff UX for Bookbot:
- Keep case progress visible across page/channel transitions.
- Add in-app notification center with deep links to the exact case step.
- Support case re-open and continuity with accessible status components.
