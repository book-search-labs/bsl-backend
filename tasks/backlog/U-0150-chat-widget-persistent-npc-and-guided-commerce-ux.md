# U-0150 — Chat Widget 실서비스 UX (고정 NPC + 가이드드 커머스 플로우)

## Priority
- P1

## Dependencies
- U-0140, U-0142, U-0144, U-0146
- B-0359, B-0370, B-0391
- U-0151, U-0152

## Goal
책봇을 모든 화면에서 우측 하단 고정 위젯으로 일관 제공하고, 주문/배송/환불 액션을 사용자가 실패 없이 완료하도록 UX를 고도화한다.

## Scope
### 1) 고정 위젯 일관성
- 페이지 이동/새로고침 후에도 위젯 상태 유지(열림/닫힘, draft, 최근 대화)
- 모바일/데스크톱에서 충돌 없는 safe-area 배치
- 긴급 공지/장애 시 위젯 상단 배너로 상태 노출

### 2) 가이드드 액션 UX
- 주문조회/배송조회/환불문의를 quick action으로 제공
- 필요 입력(orderId, 수취인, 기간) 단계형 폼으로 수집
- 입력 누락/권한 오류 시 즉시 교정 안내 + 재시도

### 3) 신뢰도/근거 UX
- 답변마다 신뢰 상태, 근거 개수, 최신성 시각화
- `근거 부족` 응답은 한국어 원인/다음 행동을 명확히 표기
- 잘못된 답변 신고 → 티켓 생성까지 2클릭 이내

### 4) 운영 전환 UX
- 상담원 전환/티켓 상태 조회 CTA 제공
- 대기 중/처리 중/해결/재오픈 상태를 채팅 내 타임라인으로 표시

## DoD
- 위젯 세션 유지율/복귀율 개선
- 커머스 지원 액션 완료율 개선
- 근거 부족 응답 후 이탈률 감소
- 티켓 전환 성공률/추적 가시성 확보
- 상세/장바구니/주문내역 진입점별 챗 전환 퍼널 지표 확보

## Codex Prompt
Upgrade chat widget UX for production:
- Keep a persistent floating widget state across pages and reloads.
- Add guided commerce flows with structured slot collection.
- Show reliability/freshness/evidence states with clear Korean fallback guidance.
- Provide fast ticket handoff and in-chat lifecycle tracking.
