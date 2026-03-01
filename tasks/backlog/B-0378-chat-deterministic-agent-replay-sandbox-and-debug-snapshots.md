# B-0378 — Chat Deterministic Agent Replay Sandbox + Debug Snapshots

## Priority
- P1

## Dependencies
- B-0350, B-0367, B-0374

## Goal
에이전트형 챗 시나리오(다중 step/tool 호출)의 실패를 로컬/스테이징에서 결정론적으로 재현해 빠르게 디버깅할 수 있게 한다.

## Scope
### 1) Replay snapshot format
- request payload, policy version, prompt template, tool I/O, budget state 스냅샷
- 시드(seed) 기반 재실행 가능 포맷 정의

### 2) Sandbox runtime
- 외부 tool 호출을 fixture/mock으로 대체 가능한 모드
- 실제 호출/모의 호출 전환 스위치 제공

### 3) Diff inspector
- 성공 실행 vs 실패 실행 경로 비교(step/tool/policy diff)
- 첫 분기점(first divergence) 자동 탐지

### 4) Shareable artifact
- RCA 티켓에 첨부 가능한 replay artifact 생성
- 민감 데이터 마스킹 후 공유

## Observability
- `chat_replay_run_total{mode,result}`
- `chat_replay_first_divergence_total{type}`
- `chat_replay_artifact_created_total`
- `chat_replay_redaction_applied_total`

## Test / Validation
- 동일 시드 재실행 결과 일관성 테스트
- mock/real 모드 전환 회귀 테스트
- divergence detector 정확성 테스트

## DoD
- 주요 장애 케이스 재현 시간 단축
- "재현 불가" 비율 감소
- replay artifact로 RCA 품질 향상

## Codex Prompt
Build deterministic replay tooling for chat agents:
- Snapshot request, policy, prompts, tool I/O, and budgets for replay.
- Run sandboxed executions with mock/real tool modes.
- Provide diff-based divergence inspection and shareable redacted artifacts.
