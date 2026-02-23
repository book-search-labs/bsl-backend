# B-0357 — Chat 품질 지표 게이트 (groundedness/hallucination/usefulness)

## Priority
- P1 (안정화 이후 지속 품질 관리)

## Dependencies
- B-0353 (근거 게이트)
- B-0358 (도메인 평가셋)

## Goal
챗봇 품질을 정량화하고, 지표 하락 시 배포를 차단하는 품질 게이트를 구축한다.

## Why
- 체감 중심 판단은 회귀를 놓치기 쉬움
- CI 게이트가 있어야 고도화 속도와 안정성을 동시에 확보 가능

## Scope
### 1) 핵심 지표 정의
- groundedness score
- hallucination rate
- answer usefulness
- abstain precision (답변 보류 정확도)
- citation coverage p50/p90

### 2) 자동 평가 파이프라인
- 정답/근거 라벨셋 기반 배치 평가
- baseline 대비 delta 판정
- 실패 케이스 top-N 자동 추출

### 3) CI/CD 연동
- PR gate: 소규모 smoke eval
- Release gate: full eval
- 실패 시 모델/프롬프트 롤백 후보 자동 표기

### 4) 운영 리포트
- 모델/프롬프트/정책 버전별 지표 비교
- 주간 리포트 자동 발행

## Gate Criteria (v1 제안)
- hallucination rate +1.5%p 이상 악화 시 실패
- groundedness -2.0%p 이상 하락 시 실패
- abstain precision -3.0%p 이상 하락 시 실패

## Non-goals
- 온라인 A/B 플랫폼 전체 구현

## DoD
- 지표가 기준치 미달이면 CI 실패
- 평가 리포트에서 실패 케이스를 즉시 추적 가능
- 기준선 업데이트 절차 문서화

## Interfaces
- `scripts/eval/chat_eval_runner.py` (예시)
- `docs/RUNBOOK.md` (gate 운영 절차)

## Codex Prompt
Add chat quality gate in CI:
- Evaluate groundedness/hallucination/usefulness/abstain precision and citation coverage.
- Compare against baseline thresholds and fail pipeline on regression.
- Publish actionable report with top failing cases.
