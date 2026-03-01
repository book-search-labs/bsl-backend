# B-0366 — Real-time Feedback Triage + Prompt Improvement Loop

## Priority
- P2

## Dependencies
- B-0284, A-0142

## Goal
사용자 피드백(👍/👎/근거부족/환각)을 실시간 triage해 프롬프트/정책 개선 루프로 연결한다.

## Scope
### 1) Feedback triage queue
- severity 기반 우선순위 큐
- 중복/유사 케이스 자동 클러스터링

### 2) Action suggestion
- 실패 유형별 추천 액션(프롬프트 수정/정책 강화/도구 라우팅 변경)

### 3) Closed-loop tracking
- 피드백 건 → 수정 PR/티켓 → 재평가 결과 연결

### 4) SLA
- high severity 피드백 처리 시간 목표 정의

## DoD
- high severity 피드백의 triage SLA 달성
- 개선 액션 이후 재발률 지표 개선

## Codex Prompt
Build real-time feedback triage loop:
- Prioritize and cluster incoming chat feedback.
- Suggest corrective actions by failure type.
- Track closed-loop outcomes from issue to re-evaluation.
