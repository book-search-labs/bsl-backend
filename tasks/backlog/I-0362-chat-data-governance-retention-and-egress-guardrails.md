# I-0362 — Chat Data Governance (Retention + Egress Guardrails)

## Priority
- P0

## Dependencies
- I-0358, I-0359
- B-0379, B-0391

## Goal
책봇 실서비스에서 대화/근거/툴로그 데이터의 보관 주기와 외부 전송(egress) 제어를 강제해 보안/규정 리스크를 줄인다.

## Scope
### 1) Retention policy enforcement
- 데이터 유형별 TTL(대화원문/요약/툴로그/피드백) 분리
- 만료 데이터 자동 삭제/익명화
- 보관 예외 승인 프로세스(운영자 승인) 제공

### 2) Egress guardrails
- 외부 LLM/외부 API 전송 필드 allowlist 강제
- 민감 필드 감지 시 자동 마스킹/차단
- egress 정책 위반 이벤트를 실시간 경보

### 3) Audit and compliance evidence
- 데이터 lifecycle 감사로그 저장
- 요청 단위로 "무엇이 어디로 전송되었는지" 추적
- 규정 점검 리포트 자동 생성

## DoD
- retention/삭제 정책이 배치 누락 없이 동작
- 민감정보 egress 위반이 실시간 차단됨
- 감사 대응 가능한 증적 리포트 자동 생성

## Codex Prompt
Harden chat data governance for production:
- Enforce retention TTLs per data class with deletion/anonymization jobs.
- Add strict egress allowlists and sensitive-field blocking.
- Produce audit evidence for data lifecycle and outbound transfers.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Retention enforcement gate 추가
  - `scripts/eval/chat_data_retention_guard.py`
  - retention lifecycle 이벤트(`data_class`, `expires_at`, `action`, `approval_id`, `trace_id/request_id`)를 분석해 overdue/삭제 커버리지/예외 승인 누락을 자동 검증
  - gate 모드에서 TTL 만료 미처리, 승인 없는 예외, trace 누락, stale window 임계치 초과 시 실패
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_data_retention_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_DATA_RETENTION_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Egress guardrails gate 추가
  - `scripts/eval/chat_egress_guardrails_gate.py`
  - outbound 이벤트(`destination`, `status`, `sensitive_field_total`, `masked`, `trace_id/request_id`)를 분석해 allowlist 위반/민감필드 비마스킹/trace 누락을 검증
  - violation 발생 시 alert coverage 비율까지 함께 체크해 실시간 경보 연계 누락을 탐지
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_egress_guardrails_gate.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_EGRESS_GUARDRAILS_GATE=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] Data governance evidence packet 추가
  - `scripts/eval/chat_data_governance_evidence.py`
  - 최신 retention/egress 게이트 리포트를 결합해 최종 상태(`READY|WATCH|HOLD`)와 권장 액션을 산출
  - lifecycle score + trace coverage를 이용해 감사 증적 품질을 계량화하고 blocker/warning을 자동 생성
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_data_governance_evidence.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_DATA_GOV_EVIDENCE_GATE=1 ./scripts/test.sh`
