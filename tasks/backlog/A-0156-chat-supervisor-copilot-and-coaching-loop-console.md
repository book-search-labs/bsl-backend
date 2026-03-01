# A-0156 — Chat Supervisor Copilot + Coaching Loop Console

## Priority
- P1

## Dependencies
- A-0154, A-0155
- B-0397, B-0357

## Goal
운영 슈퍼바이저가 책봇/상담원 처리 품질을 동시에 모니터링하고, 실패 패턴 기반 코칭 액션을 즉시 실행할 수 있도록 한다.

## Scope
### 1) Supervisor copilot view
- 세션별 위험도, 해결 단계, 이관 상태를 실시간 타임라인으로 제공
- "재질문 필요", "정책 예외 검토", "즉시 이관" 추천 액션 제시
- 추천 액션 적용 시 결과 추적(성공/실패) 기록

### 2) Coaching loop
- 반복 실패 패턴을 상담원/플로우 단위로 집계
- 코칭 템플릿(금칙 응답, 확인 질문 순서, 정책 설명 방식) 제공
- 코칭 적용 전/후 해결률 변화 비교 리포트

### 3) Governance integration
- 고위험 세션은 품질 검수 큐로 자동 라우팅
- 검수 결과를 평가셋/정책 개정 후보로 자동 연결
- 주간 운영 리뷰 자료 자동 생성

## DoD
- 슈퍼바이저가 고위험 세션을 신속히 선별하고 개입 가능
- 코칭 루프 적용 후 반복 실패율이 감소
- 검수/코칭 데이터가 정책 개선 파이프라인으로 자동 연동됨

## Codex Prompt
Create a supervisor copilot console for chat operations:
- Surface risky sessions with actionable intervention recommendations.
- Run a coaching loop from recurring failure patterns.
- Connect QA/coaching outcomes back to policy and evaluation pipelines.
