# B-0396 — Chat Actionability Scorer + Repair Loop

## Priority
- P0

## Dependencies
- B-0357, B-0393, B-0395
- I-0353

## Goal
책봇 답변이 "설명만 있는 답변"에 머물지 않고, 사용자가 즉시 실행 가능한 다음 행동을 항상 제공하도록 보장한다.

## Scope
### 1) Actionability scorer
- 답변별 실행가능성 점수(`actionability_score`) 계산
- 최소 구성요소(현재 상태/다음 행동/예상 결과/실패시 대안) 충족 여부 검사
- intent별 최소 점수 컷라인 정의(주문/배송/환불/일반)

### 2) Repair loop
- 점수 미달 답변은 자동 재작성 경로로 전환
- 재작성 시 누락 슬롯(주문번호, 상태, 수수료 등) 우선 보강
- 2회 재작성 실패 시 안전한 상담 전환 템플릿으로 fail-closed

### 3) Claim-to-action consistency
- 제시한 행동이 실제 tool/policy 결과와 일치하는지 검증
- 실행 불가 행동(정책 위반/권한 부족/상태 불일치) 자동 제거
- 행동-결과 불일치 탐지 시 reason_code 기반 경고 생성

### 4) Release gate integration
- actionability 기준 미달 응답 비율이 임계치 초과 시 canary 승격 차단
- 저품질 intent bucket만 부분 격리/롤백 가능하도록 정책화

## Observability
- `chat_actionability_score_hist{intent}`
- `chat_actionability_repair_total{intent,result}`
- `chat_actionability_fail_closed_total{reason_code}`
- `chat_claim_action_mismatch_total{intent}`

## Test / Validation
- intent별 actionability golden set 회귀 테스트
- repair 성공/실패 및 fail-closed 경로 테스트
- actionability gate가 릴리스 파이프라인에서 정상 차단되는지 검증

## DoD
- 저품질 안내성 답변 비율이 운영 목표 이하로 유지됨
- 사용자 관점 "다음 행동 모호" 피드백이 유의미하게 감소
- actionability 지표가 운영 대시보드와 릴리스 게이트에 연결됨

## Codex Prompt
Add actionability guarantees for production chat:
- Score whether responses provide executable next actions.
- Auto-repair low-actionability responses with slot completion.
- Fail closed to safe handoff when repairs cannot meet policy/tool constraints.
