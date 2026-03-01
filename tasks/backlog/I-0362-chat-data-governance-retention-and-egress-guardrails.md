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
