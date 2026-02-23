# A-0142 — Chat Failure Triage Workbench (Replay/Diff/RCA)

## Priority
- P1

## Dependencies
- B-0350, A-0140

## Goal
운영자가 실패 케이스를 즉시 재현하고 버전 간 결과 차이를 비교해 RCA를 빠르게 수행하도록 한다.

## Scope
### 1) Replay UI
- request_id로 재실행
- 동일 조건/최신 조건 비교

### 2) Diff view
- 답변 diff
- citations diff
- stage latency diff

### 3) RCA 템플릿
- 원인 분류, 임시조치, 영구조치 기록

## DoD
- 실패 케이스 1건 RCA 완료 시간 단축
- replay/diff 결과를 티켓으로 바로 이관 가능

## Codex Prompt
Build admin triage workbench for chat failures:
- Add replay by request_id and result diff views.
- Include latency/citation diffs and RCA note workflow.
