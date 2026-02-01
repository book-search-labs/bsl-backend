# B-0272 — RS(orchestrator) ↔ MIS 계약 고정 + 부하테스트(배치/latency) + Canary-ready

## Goal
Ranking Service(RS)가 MIS를 안정적으로 호출하도록 **계약(Contract)을 고정**하고,
운영 기준의 **부하 테스트/회귀 테스트**를 붙인다.

- RS는 orchestration/feature assembly에 집중
- MIS는 inference(embedding/rerank)에 집중
- 계약이 깨지면 CI에서 막는다(compat gate는 B-0226 연계)

## Background
- “모델 서버”는 자주 바뀐다(버전/최적화/스케일).
- RS↔MIS는 계약을 고정하지 않으면 운영 중 장애가 난다.
- latency budget을 넘으면 SR이 연쇄 degrade 되므로, 성능 테스트가 필수.

## Scope
### 1) Contract definition
- OpenAPI(or JSON Schema)로:
  - `/v1/score` req/res
  - 에러 스키마
  - 모델 목록(`/v1/models`)
- versioning:
  - major/minor 규칙
  - breaking change 차단

### 2) RS integration
- RS에서:
  - 후보 topR 준비(필드 제한 + best_chunk 포함)
  - MIS 호출 timeout 설정
  - 실패 시 fallback 규칙(점수 없이 원래 순서 유지 등)
- request_id/trace_id 전파

### 3) Load test suite (필수)
- tool:
  - k6 / locust / vegeta 중 1
- 시나리오:
  - topR=20/50/100
  - 동시성 1/5/20/50
  - timeout 경계 테스트
- 산출물:
  - p50/p95/p99 latency
  - error rate
  - throughput
  - CPU/RAM 사용량(간단 기록)

### 4) Canary-ready hooks (준비만)
- request에 `model_version` 지정 가능
- 또는 header로 `x-model-version`
- (실제 routing은 B-0274)

## Non-goals
- 모델 레지스트리 라우팅 구현(=B-0274)
- SR의 fallback 전체 정책(=B-0273)

## DoD
- RS↔MIS contract 파일이 repo에 존재하고 CI에서 검증됨
- RS가 MIS 호출 + timeout + fallback 처리 완료
- 부하 테스트 리포트(마크다운) 생성
- latency budget 충족 여부 명시(기준 미달 시 knobs 안내 포함)

## Codex Prompt
Lock RS↔MIS contract and performance:
- Define OpenAPI/JSON schema for /v1/score and error responses.
- Integrate RS to call MIS with strict timeouts and propagate request_id/trace_id.
- Add k6/locust load test scenarios for topR=20/50/100 and concurrency sweeps.
- Produce a markdown report with p50/p95/p99, error rate, and resource notes.
