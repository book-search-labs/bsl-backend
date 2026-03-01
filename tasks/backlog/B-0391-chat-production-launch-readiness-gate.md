# B-0391 — Chat Production Launch Readiness Gate (실서비스 출시 게이트)

## Priority
- P0

## Dependencies
- B-0351, B-0352, B-0353, B-0359
- B-0368, B-0370, B-0383, B-0390
- I-0353, I-0354, I-0355
- B-0392, B-0393

## Goal
책봇을 "실서비스 가능" 수준으로 출시하기 위한 백엔드 출시 게이트를 정의하고 자동 검증 파이프라인으로 강제한다.

## Non-goals
- 신규 LLM 모델 연구/교체 자체가 목표가 아니다.
- UI 재디자인 전체를 포함하지 않는다.
- 커머스 도메인 정책 원문 작성 책임을 대체하지 않는다.

## Scope
### 1) 출시 게이트 기준 (hard gate)
- groundedness, citation coverage, task completion, safety violation, latency, cost에 대한 기준선 고정
- 기준 미달 시 canary 승격 차단 및 자동 rollback 트리거
- 한국어 질의셋(환불/배송/주문/정책) 별도 컷라인 적용

### 2) 답변 신뢰성 강제
- `insufficient_evidence` 응답 시 한국어 안내 템플릿 강제
- 증거 부족/정책 미확정/권한 부족을 reason_code로 분리
- reason_code별 재시도/상담전환/티켓생성 정책 연결

### 3) 커머스 질의 완료율 강화
- 주문/배송/환불 인텐트에서 tool-required 경로 강제
- 필수 슬롯(orderId, 기간, 본인확인) 미충족 시 질문 루프 표준화
- "대답은 했지만 액션 실패" 케이스를 completion 실패로 집계

### 4) 회귀/재현성
- 릴리스마다 고정 evalset + 시드 기반 재현 리포트 생성
- 실패 케이스 자동 샘플링 후 triage queue 적재
- 모델/프롬프트/정책 버전별 비교 리포트 자동 생성

## Interfaces
- `POST /v1/chat`
- `POST /v1/chat/feedback`
- Internal: eval runner / policy checker / release gate API

## Data / Schema
- `chat_release_gate_result` (new): build_id, model_version, prompt_version, policy_version, metrics, pass_fail
- `chat_answer_failure_case` (new): reason_code, query, tool_trace, citation_snapshot, severity
- 계약(`contracts/**`) 변경이 필요한 경우 별도 PR 분리

## Observability
- `chat_launch_gate_pass_total{env}`
- `chat_launch_gate_block_total{reason}`
- `chat_completion_rate{intent}`
- `chat_insufficient_evidence_rate{domain}`
- `chat_reason_code_total{reason_code}`

## Test / Validation
- 한국어 실서비스 시나리오 회귀셋(주문/배송/환불/반품/정책) 200+ 케이스
- 장애 주입(LLM timeout/tool 5xx/schema mismatch) 시 degrade 정책 검증
- 출시 게이트 fail 시 배포 차단 E2E 테스트

## DoD
- 출시 게이트가 CI/CD에서 강제되고, fail-open 없이 동작
- reason_code 기반 한국어 fallback 표준화 완료
- 커머스 인텐트 completion 지표를 대시보드에서 실시간 확인 가능
- 배포 승인 근거 리포트(품질/안전/비용) 자동 생성
- preflight 체크리스트(데이터거버넌스/운영승인/릴리스감사)가 자동 검증됨

## Codex Prompt
Implement production launch gates for chat:
- Define hard quality/safety/cost thresholds and block release when violated.
- Enforce Korean fallback templates with explicit reason codes.
- Track true task completion for commerce intents and fail unresolved runs.
- Generate reproducible release reports per model/prompt/policy version.
