# I-0363 — Chat Production Load Model + Capacity Forecasting

## Priority
- P0

## Dependencies
- I-0355, I-0360, I-0361
- B-0394

## Goal
책봇 트래픽/비용/성능을 예측 가능한 운영 모델로 관리하기 위해 부하 모델과 용량 예측 체계를 구축한다.

## Scope
### 1) Load model
- 시간대/의도/툴사용률 기반 부하 모델 구축
- 정상/프로모션/장애 상황별 트래픽 프로파일 정의
- 대기열/지연/실패율 임계치 연계

### 2) Capacity forecasting
- 주간/월간 요청량, 토큰 사용량, 툴 호출량 예측
- 모델별 필요 리소스(CPU/GPU/메모리) 산출
- 비용 예측과 예산 경보 연계

### 3) Auto scaling policy calibration
- 예측 기반 사전 스케일업 정책
- 과잉 스케일/과소 스케일 탐지 및 정책 자동 조정
- 릴리스 이벤트 전후 capacity canary 검증

## DoD
- 월 단위 수요 예측 오차율이 관리 목표 내 유지
- 피크 시간대 SLO 위반률 감소
- 스케일링 정책의 과잉/부족 할당이 감소

## Codex Prompt
Operationalize chat capacity forecasting:
- Build load profiles by intent/time/tool usage.
- Forecast demand and resource needs with budget linkage.
- Calibrate autoscaling policies using prediction and canary validation.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Load profile model 게이트 추가
  - `scripts/eval/chat_load_profile_model.py`
  - 트래픽 이벤트(JSONL)를 기준으로 `NORMAL|PROMOTION|INCIDENT` 시나리오별 request/error/tool usage/p95 latency/p95 queue depth를 집계
  - 시간대(hour UTC) 분포와 상위 intent 분포를 함께 리포팅해 운영 부하 모델 기준선 생성
  - gate 모드에서 NORMAL 구간의 error/latency/queue 임계치 위반 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_load_profile_model.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_LOAD_PROFILE_MODEL=1 ./scripts/test.sh`
