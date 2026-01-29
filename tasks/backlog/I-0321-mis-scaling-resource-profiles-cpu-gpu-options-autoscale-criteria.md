# I-0321 — MIS 스케일링/리소스 프로파일 (CPU/GPU 옵션) + 오토스케일 기준

## Goal
MIS를 CPU/GPU 환경에서 안정적으로 돌리고,
동시성/큐/배치에 대한 “리소스 프로파일”을 만들고 오토스케일 기준을 세운다.

## Why
- reranker/cross-encoder는 추론 비용이 크고, 병목이 쉽게 생김
- 스케일 기준이 없으면 p99이 터지거나 비용이 터짐

## Scope
### 1) 프로파일링 시나리오
- 입력 길이/후보수(topR)/batch size 별 latency 측정
- CPU 1~N core, GPU 1장(선택)
- QPS ramp test로 saturation point 찾기

### 2) 설정 파라미터 고정
- `max_batch_size`, `max_queue_size`, `max_seq_len`, `timeout_ms`
- dynamic batching on/off
- concurrency(워크 수)

### 3) 오토스케일 기준
- CPU util
- queue depth(가장 중요)
- p95 latency
- (GPU) GPU util / memory

### 4) 런북/알람 연결
- scale-out/scale-in 시나리오
- 과부하 시 degrade 정책(연계: I-0317, I-0316)

## Non-goals
- 멀티 GPU 분산 추론(추후)

## DoD
- “권장 리소스/설정 조합” 문서화(예: CPU-only baseline, GPU option)
- 오토스케일 룰이 정의되고 stage에서 동작 검증
- 과부하 시 queue 기반으로 scale + degrade가 작동

## Codex Prompt
Create MIS scaling profiles:
- Benchmark MIS latency under varying batch/concurrency/topR/seq_len on CPU (and GPU if available).
- Define recommended configs and autoscaling rules based on queue depth and latency.
- Document in runbook and wire alerts.
