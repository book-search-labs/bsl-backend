# B-0373 — Chat Adversarial Evalset + Korean Safety Regression Gate

## Priority
- P1

## Dependencies
- B-0357, B-0358, B-0356

## Goal
한국어 중심 악성/교란/오해 유발 질의 평가셋을 확장해, 챗봇 안전성 회귀를 배포 전에 차단한다.

## Scope
### 1) Adversarial dataset
- prompt injection, role confusion, fake policy, 감정 유도형 압박 케이스 수집
- 한국어/CJK 혼합 사례와 커머스 도메인 사례 포함

### 2) Safety metrics
- jailbreak success rate, unsafe action execution rate, abstain precision
- false refusal rate(정상 요청 과잉거절) 동시 추적

### 3) CI gate integration
- PR gate(샘플셋), release gate(풀셋) 분리
- 임계치 초과 시 빌드 실패

### 4) Drift tracking
- 월별 평가셋 갱신 및 버전 관리
- 실사용 실패사례를 평가셋으로 환류

## Observability
- `chat_safety_eval_pass_rate{suite}`
- `chat_jailbreak_success_total{suite}`
- `chat_false_refusal_total{suite}`
- `chat_safety_gate_block_total{stage}`

## Test / Validation
- 안전성 평가 러너 단위 테스트
- 게이트 실패 시 리포트 생성/아티팩트 저장 확인
- 회귀 차단 케이스 재현 테스트

## DoD
- 한국어 안전성 회귀가 CI에서 자동 차단
- red-team 케이스 커버리지 지속 확장
- 과잉거절/과소차단 균형 지표를 정기 보고

## Codex Prompt
Strengthen Korean chat safety evaluation:
- Build adversarial eval suites for injection, policy spoofing, and unsafe actions.
- Gate PR/release on safety and false-refusal thresholds.
- Continuously refresh datasets from real incident feedback.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Adversarial dataset coverage gate 추가
  - `scripts/eval/chat_adversarial_dataset_coverage.py`
  - 필수 공격유형(prompt injection/role confusion/fake policy/emotional pressure) 커버리지 검증
  - Korean ratio, CJK mixed, commerce-domain 케이스 분포를 게이트화
  - gate 모드에서 coverage 부족/invalid case 초과 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_adversarial_dataset_coverage.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_ADVERSARIAL_DATASET_COVERAGE=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Safety metrics gate 추가
  - `scripts/eval/chat_adversarial_safety_metrics.py`
  - jailbreak success rate, unsafe action execution rate, abstain precision, false refusal rate를 동시 검증
  - label 누락 및 stale evidence를 함께 게이트화
  - gate 모드에서 임계치 초과/미달 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_adversarial_safety_metrics.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_ADVERSARIAL_SAFETY_METRICS=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] PR/Release stage gate 추가
  - `scripts/eval/chat_adversarial_ci_gate.py`
  - Bundle 1(coverage) + Bundle 2(metrics) 리포트를 결합해 stage별 임계치 평가
  - report 누락(require-reports), evidence stale, stage별 quality threshold 위반을 게이트화
  - gate 모드에서 `PASS/BLOCK` decision과 failure reason 출력
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_adversarial_ci_gate.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_ADVERSARIAL_CI_GATE=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Drift tracking gate 추가
  - `scripts/eval/chat_adversarial_drift_tracking.py`
  - 월별 dataset refresh gap, dataset version 증가, refresh age를 게이트화
  - incident feedback의 dataset case 링크 비율/미연결 건수 추적
  - gate 모드에서 drift evidence stale 포함 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_adversarial_drift_tracking.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_ADVERSARIAL_DRIFT_TRACKING=1 ./scripts/test.sh`
