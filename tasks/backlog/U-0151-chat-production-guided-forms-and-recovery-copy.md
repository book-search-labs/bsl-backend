# U-0151 — Chat 실서비스 가이드드 폼 + 복구 카피 UX

## Priority
- P1

## Dependencies
- U-0150
- B-0391, B-0392

## Goal
책봇 대화 중 사용자 입력 누락/오입력/실패 복구를 줄이기 위해 가이드드 폼과 한국어 복구 카피 체계를 도입한다.

## Scope
### 1) Guided forms
- 주문번호/기간/수취정보 입력을 단계형 폼으로 제공
- 입력 형식 실시간 검증(길이/패턴/필수값)
- 유효성 실패 시 즉시 교정 힌트 제공

### 2) Recovery copy system
- reason_code별 고정 한국어 카피 세트 운영
- 실패 후 다음 행동(재시도/다른 경로/상담 전환) CTA 명확화
- 동일 오류 반복 시 자동으로 단축 경로 제안

### 3) Context-preserving retry
- 재시도 시 기존 입력값 유지
- 페이지 이동/새로고침 후에도 마지막 진행 단계 복구
- 취소/초기화 액션을 명확히 분리

## DoD
- 폼 입력 오류율 감소
- 실패 후 재시도 성공률 개선
- 반복 질문율/이탈률 감소

## Codex Prompt
Upgrade chat UX for production recovery:
- Add guided slot forms with inline validation.
- Standardize Korean recovery copy by reason code.
- Preserve user context across retries/navigation/reloads.
