# I-0342 — Chaos/Degrade 리허설(의존 서비스 다운 시나리오) + Runbook 보강

## Goal
“장애가 났을 때 어떻게 안전하게 계속 서빙할지”를 미리 연습하고 문서화한다.
- 의존 서비스가 다운되더라도 **검색은 0건이 아니라 degraded 결과를 반환**
- 운영자가 즉시 취할 액션(토글/롤백/스케일)을 Runbook에 고정한다.

## Why
- SR/RS/MIS/QS/OS/Kafka 중 하나만 흔들려도 전체 UX가 깨짐
- 운영형 시스템은 “성능 하락은 허용, 완전 장애는 최소화”가 기본

## Scope
### 1) Chaos 시나리오 정의(최소)
- OpenSearch 지연/부분 실패
- MIS 다운(리랭킹 불가)
- QS 2-pass 타임아웃/LLM 오류
- Kafka 장애(outbox backlog 증가)
- Redis 장애(AC cache miss 증가)

### 2) 기대 동작(Degrade 정책)
- vector off → bm25-only
- rerank off → fused 순서로 응답
- QS 2-pass off → 1-pass만
- AC: OS miss path로 전환 + rate-limit 강화
- 이벤트: outbox에 적재 후 재전송(유실 금지)

### 3) 리허설 실행
- stage 환경에서 강제로 장애 주입(컨테이너 stop/latency injection 등)
- p95/p99, error rate, 0-result-rate 변화 기록

### 4) Runbook 업데이트(I-0316 연계)
- “알람 발생 → 5분 내 액션” 체크리스트
- 토글 위치/명령어/롤백 절차

## Non-goals
- 완전한 chaos engineering 플랫폼 도입(예: Gremlin)까지는 안 함

## DoD
- 최소 3개 장애 시나리오 리허설 완료 + 결과 기록
- Runbook에 “즉시 액션” 절차가 반영됨
- 실제로 degraded 응답이 반환되는지 검증(0건 방지)

## Codex Prompt
Add chaos/degrade drills:
- Define failure scenarios and expected degrade behaviors per service.
- Create simple scripts to simulate outages/latency in stage.
- Update runbook with step-by-step mitigation actions and verify via metrics.
