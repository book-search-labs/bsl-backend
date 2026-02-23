# A-0155 — Chat Outcome Review + Rollback Decision Console

## Priority
- P1

## Dependencies
- A-0153, A-0154
- B-0357, B-0396

## Goal
운영자가 릴리스 후 성과(해결률/재문의율/위험도)를 빠르게 검토하고, 부분 롤백 여부를 즉시 결정할 수 있는 콘솔을 제공한다.

## Scope
### 1) Outcome review dashboard
- intent bucket별 해결률/재문의율/actionability score 추이 제공
- 정책/프롬프트/모델 버전별 성과 비교
- 이상치 구간 자동 하이라이트 및 원인 후보 제시

### 2) Rollback decision workflow
- 전면 롤백/부분 롤백(특정 인텐트/정책 버전) 실행 플로우
- 롤백 영향 범위(트래픽, 예상 품질/비용 변화) 사전 미리보기
- 승인자 2인 규칙(옵션) 및 실행 감사로그 기록

### 3) Evidence and audit bundle
- 결정 시점의 KPI 스냅샷/실패 사례/티켓 링크 자동 첨부
- 사후 회고 템플릿 자동 생성
- 규정 감사용 export 제공

## DoD
- 성과 저하 발생 시 10분 내 롤백 여부 판단이 가능
- 부분 롤백 실행 이력과 근거가 완전하게 저장
- 회고/개선 티켓 연계가 자동화됨

## Codex Prompt
Create an admin post-release decision console:
- Review chat outcomes by intent and version with anomaly cues.
- Support full/partial rollback decisions with impact preview.
- Persist auditable decision evidence and retrospective links.
