# I-0316 — Runbook / On-call (장애 대응 절차)

## Goal
운영 중 장애가 발생했을 때 “누가 봐도” 따라 할 수 있는
**Runbook(대응 절차) + On-call 기준**을 문서화한다.

## Why
- 운영의 성패는 코드보다 “복구 속도/일관성”에서 갈림
- BSL은 서비스가 많아서, 장애 시 원인 추적이 복잡해짐

## Scope
### 1) 공통 Runbook
- Incident triage:
  - 1) 증상 분류(5xx/timeout/0-results/latency spike)
  - 2) 영향 범위(특정 API? 특정 서비스?)
  - 3) 즉시 완화(degrade 모드, feature flag off, rerank off, hybrid off)
- 로그/트레이스 확인 순서:
  - request_id/trace_id로 end-to-end 추적
- 롤백 절차:
  - 배포 롤백(I-0315 연계)
  - 모델 롤백(B-0274 연계)
  - 인덱스 alias 롤백(B-0223/0224 연계)

### 2) 시나리오별 Runbook(최소)
- OpenSearch 장애/지연:
  - degraded(bm25-only, cached SERP)
  - query timeout 튜닝
- Kafka 지연/DLQ 증가:
  - outbox backlog 처리
  - replayer 실행(Phase 10/I-0340 연계)
- MIS 장애:
  - rerank off → fusion 결과 반환
- ETL/Index job 실패:
  - job_run 확인 → 재시도 → 스냅샷/복구(I-0308 연계)

### 3) On-call 기준(간단)
- 알람 기준:
  - error rate, p99 latency, 0-results rate, outbox backlog, consumer lag
- Escalation:
  - 누구에게/어떤 순서로/어떤 정보 포함

## Non-goals
- 24/7 실제 당직 운영(포트폴리오 단계에서는 문서화 중심)

## DoD
- `docs/RUNBOOK.md` 작성
- 최소 3개 장애 시나리오 리허설(로컬/스테이징)
- “즉시 완화 토글”(rerank/hybrid/2-pass) 목록과 방법이 문서에 포함

## Codex Prompt
Create operational runbooks:
- Write RUNBOOK.md covering triage, mitigation toggles, rollback steps, and service-specific failure playbooks.
- Include how to use request_id/trace_id across services.
- Add alarm thresholds and an on-call escalation checklist.
