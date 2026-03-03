# B-0724 — Performance Budget Cutover + Legacy Decommission

## Priority
- P2

## Dependencies
- B-0714
- B-0723

## Goal
전면 리라이트 엔진의 성능/비용/SLO를 검증한 뒤 안전하게 cutover하고 legacy 엔진을 단계적으로 폐기한다.

## Scope
### 1) Performance budget
- 경로별 p95/p99 목표 정의(non-LLM vs LLM)
- 토큰/호출량/툴 호출량 budget 상한 설정
- 성능 예산 위반 시 자동 경고/승격 차단

### 2) Cutover plan
- 트래픽 단계: 10% -> 25% -> 50% -> 100%
- 각 단계별 minimum dwell time 및 승격 조건
- 실패 시 자동/수동 rollback 경로 병행

### 3) Legacy decommission
- 2주 안정화 후 legacy read-path 비활성화
- legacy 전용 코드/플래그/대시보드 정리 계획
- decommission 체크리스트 문서화

### 4) Post-cutover verification
- SLO, 비용, 오실행, 권한 사고 지표 추적
- 운영 리뷰(주간)와 잔여 리스크 등록

## Test / Validation
- load/perf tests
- rollout + rollback drill tests
- post-cutover smoke and incident simulation tests

## DoD
- 100% 전환 후 SLO와 비용 예산을 유지한다.
- legacy 복구 경로를 제외한 주 실행 경로가 정리된다.
- 운영팀이 cutover/decommission 절차를 runbook대로 재현 가능하다.

## Codex Prompt
Complete rewrite rollout with performance/cost safeguards:
- Define cutover budgets and promotion gates.
- Run staged traffic migration with rollback drills.
- Decommission legacy engine safely after stabilization.

---

## Implementation Update (Bundle 1)

- `chat_cutover_gate.py`를 리포트/게이트형 스크립트로 승격:
  - report JSON/Markdown 생성 (`report_json`, `report_md` 표준 출력)
  - `--gate` 모드에서 fail-fast(exit 2) 지원
  - `--require-promote` 옵션 추가(hold 허용 여부 제어)
- cutover gate 판정 로직 분리:
  - `evaluate_cutover(...)`로 parity/perf/cutover/rollback 계산 분리
  - `evaluate_gate(...)`로 parity/perf 실패 및 rollback 액션 차단 규칙 고정
- 테스트 추가:
  - `scripts/eval/test_chat_cutover_gate.py`
    - hold 허용 패스
    - parity/perf 실패 + rollback 실패
    - require-promote 활성 시 hold 차단
- `scripts/test.sh` 연동 강화:
  - `RUN_CHAT_CUTOVER_GATE=1` 실행 시 `--gate` 기본 적용
  - `CHAT_CUTOVER_REQUIRE_PROMOTE=1`로 strict promote 모드 지원

## Implementation Update (Bundle 2)

- `chat_legacy_decommission_check.py`를 리포트/베이스라인 비교형 게이트로 확장:
  - report JSON/Markdown 생성 + 표준 출력(`report_json`, `report_md`, `gate_pass`)
  - `--baseline-report` + drift 임계치(`--max-legacy-count-increase`, `--max-legacy-ratio-increase`) 지원
  - gate 실패 시 fail-fast(exit 2) 및 baseline 실패 원인 분리 출력
- baseline 비교 로직 추가:
  - `compare_with_baseline(...)`로 legacy_count/legacy_ratio 회귀 감지
- 테스트/운영 연동:
  - `scripts/eval/test_chat_legacy_decommission_check.py`에 baseline 회귀 테스트 추가
  - baseline fixture 추가:
    - `services/query-service/tests/fixtures/chat_legacy_decommission_baseline_v1.json`
  - `scripts/test.sh`의 `RUN_CHAT_LEGACY_DECOMMISSION_CHECK=1` 경로에 baseline/diff threshold 인자 연결

## Implementation Update (Bundle 3)

- `chat_release_train_gate.py`를 fail-fast 리포트 게이트로 승격:
  - `--gate`, `--require-promote`, `--out`, `--prefix` 옵션 추가
  - gate 규칙: rollback action 차단 + optional promote 강제
  - report JSON/Markdown 출력(`report_json`, `report_md`, `gate_pass`)
- 테스트 강화:
  - `scripts/eval/test_chat_release_train_gate.py`
    - rollback action 실패 검증
    - require-promote 활성 시 hold 차단 검증
- `scripts/test.sh` 연동:
  - `RUN_CHAT_RELEASE_TRAIN_GATE=1` 경로에서 `--gate` 기본 적용
  - `CHAT_RELEASE_TRAIN_REQUIRE_PROMOTE=1`로 strict promote 모드 지원
