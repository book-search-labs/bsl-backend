# A-0154 — Chat Resolution Ops + Policy Exception Console

## Priority
- P1

## Dependencies
- A-0151, A-0153
- B-0395, I-0362

## Goal
운영자가 "해결 실패 세션"과 "정책 예외 요청"을 빠르게 처리해 실서비스 품질 저하를 최소화한다.

## Scope
### 1) Resolution failure queue
- 미완료 세션을 reason_code/intent/SLA 지연 기준으로 우선순위 정렬
- 세션별 요약 플랜, 실패 단계, tool 결과, 사용자 피드백을 한 화면에서 확인
- 재실행 가능 액션(재시도/대체경로/상담이관) 제공

### 2) Policy exception workflow
- 표준 정책으로 처리 불가한 케이스에 대해 예외 승인 플로우 제공
- 승인/반려 사유 템플릿화 및 감사로그 저장
- 예외 정책은 유효기간/적용범위/승인자 이력을 강제

### 3) QA and governance integration
- 고빈도 실패 패턴을 주간 품질 리뷰 항목으로 자동 등록
- 예외 승인 건을 리그레션 테스트 후보셋으로 자동 추출
- 릴리스 전 미해결 고위험 항목이 있으면 경고/차단

## DoD
- 운영자가 실패 세션의 원인과 다음 조치를 1분 내 판단 가능
- 정책 예외 승인 이력이 감사 가능한 형태로 누락 없이 저장
- 반복 실패 패턴이 품질 개선 루프(티켓/평가셋)로 자동 연결됨

## Codex Prompt
Build an admin console for unresolved chat cases:
- Prioritize failed resolution sessions by risk and SLA impact.
- Add policy-exception approval workflow with full auditability.
- Feed recurring failure patterns into QA/regression and release gates.
