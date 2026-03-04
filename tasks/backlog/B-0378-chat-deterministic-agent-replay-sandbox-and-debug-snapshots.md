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

## Implementation Update (2026-03-03, Bundle 1)
- [x] Replay snapshot format gate 추가
  - `scripts/eval/chat_replay_snapshot_format.py`
  - request payload/policy version/prompt template/tool I/O/budget state/seed 필수 필드 검증
  - snapshot stale 여부 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_replay_snapshot_format.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REPLAY_SNAPSHOT_FORMAT=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Replay sandbox runtime gate 추가
  - `scripts/eval/chat_replay_sandbox_runtime.py`
  - mock/real 모드 parity mismatch 검증
  - 동일 seed 비결정성(non-deterministic) 검증
  - mode/result/seed/response hash 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_replay_sandbox_runtime.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REPLAY_SANDBOX_RUNTIME=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Replay diff inspector gate 추가
  - `scripts/eval/chat_replay_diff_inspector.py`
  - 정상/실패 replay의 first divergence 자동 탐지 검증
  - divergence type 분류(POLICY/TOOL_IO/PROMPT/BUDGET/STATE/OUTPUT) 검증
  - missing first divergence / unknown type / invalid step / stale 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_replay_diff_inspector.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REPLAY_DIFF_INSPECTOR=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Replay artifact shareability gate 추가
  - `scripts/eval/chat_replay_artifact_shareability.py`
  - replay artifact 생성/공유 가능성 검증
  - redaction 적용 여부 및 unmasked sensitive 탐지
  - ticket reference 누락 및 invalid share scope 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_replay_artifact_shareability.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_REPLAY_ARTIFACT_SHAREABILITY=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 5)
- [x] Baseline drift governance 추가 (replay 4종 공통)
  - `scripts/eval/chat_replay_snapshot_format.py`
  - `scripts/eval/chat_replay_sandbox_runtime.py`
  - `scripts/eval/chat_replay_diff_inspector.py`
  - `scripts/eval/chat_replay_artifact_shareability.py`
  - `--baseline-report` + `compare_with_baseline(...)` + `gate.baseline_failures` + `source/derived.summary` + `gate_pass` 출력 반영
- [x] baseline 회귀 테스트 추가
  - `scripts/eval/test_chat_replay_snapshot_format.py`
  - `scripts/eval/test_chat_replay_sandbox_runtime.py`
  - `scripts/eval/test_chat_replay_diff_inspector.py`
  - `scripts/eval/test_chat_replay_artifact_shareability.py`
- [x] CI baseline wiring + drift env 확장
  - `scripts/test.sh` (step 88~91)
  - baseline fixture 자동 연결 + `*_DROP`, `*_INCREASE` env 반영
- [x] 운영 문서 업데이트
  - `docs/RUNBOOK.md` B-0378 섹션에 baseline 실행 예시/CI drift env 추가
