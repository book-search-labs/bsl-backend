# A-0151 — Chat QA 판정 큐 + 정책 승인 워크플로우

## Priority
- P1

## Dependencies
- A-0150
- B-0391, B-0353, B-0383

## Goal
운영자가 책봇 실패 케이스를 빠르게 판정하고 정책/프롬프트 수정안을 승인-배포까지 추적할 수 있는 QA 판정 큐를 제공한다.

## Scope
### 1) QA adjudication queue
- 근거 부족/환각/권한오류/툴실패 케이스 큐잉
- 증거 스냅샷 + 답변 + reason_code + tool trace 한 화면 제공
- 판정 라벨(정상/개선필요/치명) 저장

### 2) Policy approval workflow
- 정책/프롬프트 변경안의 승인 단계(작성→검토→승인→배포)
- 고위험 변경은 2인 승인 옵션
- 승인 이력/근거를 감사로그로 저장

### 3) Feedback loop linkage
- 판정 결과를 개선 티켓 자동 생성으로 연결(옵션)
- 배포 후 동일 케이스 재발률 추적

## DoD
- 실패 케이스 triage lead time 단축
- 승인 워크플로우가 감사 가능 상태로 정착
- 개선 배포 후 재발률 추세를 추적 가능

## Codex Prompt
Build admin QA adjudication for chat:
- Queue and review failure cases with full evidence context.
- Add policy/prompt approval workflow with audit trail.
- Link adjudication outcomes to improvement tickets and recurrence tracking.
