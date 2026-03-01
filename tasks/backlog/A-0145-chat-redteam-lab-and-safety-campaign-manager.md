# A-0145 — Chat Red-team Lab + Safety Campaign Manager

## Priority
- P2

## Dependencies
- A-0142, A-0143, B-0373

## Goal
운영자가 정기 레드팀 캠페인을 설계/실행/추적해 챗봇 안전성 취약점을 체계적으로 발견하고 개선한다.

## Scope
### 1) Campaign setup
- 시나리오 세트, 대상 버전, 기간, 통과 기준 설정
- 도메인별(검색/주문/환불/이벤트) 캠페인 템플릿

### 2) Execution dashboard
- 캠페인 진행률, 실패유형, 우선조치 대상 시각화
- 반복 실패 케이스 클러스터링

### 3) Action tracking
- 취약점 -> 티켓 생성 -> 수정 검증 -> 재테스트 연결
- 잔여 리스크 목록 및 담당자 지정

### 4) Governance evidence
- 캠페인 결과 리포트와 승인 로그 저장
- 릴리즈 승인 조건과 연결

## DoD
- 월 1회 이상 레드팀 캠페인 운영 가능
- 취약점 대응 리드타임 단축
- 안전성 릴리즈 의사결정 근거가 감사 가능

## Codex Prompt
Build a red-team operations console for chat safety:
- Plan and execute scenario campaigns with pass/fail criteria.
- Track vulnerability remediation from finding to re-test.
- Persist governance evidence for release approval workflows.
