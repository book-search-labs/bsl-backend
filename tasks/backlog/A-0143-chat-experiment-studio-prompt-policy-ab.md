# A-0143 — Chat Experiment Studio (Prompt/Policy A-B)

## Priority
- P2

## Dependencies
- A-0141, I-0352

## Goal
운영자가 프롬프트/정책 실험을 안전하게 설계·실행·평가할 수 있는 관리 기능을 제공한다.

## Scope
### 1) Experiment setup
- 대상 버전, 트래픽 비율, 대상 세그먼트 설정

### 2) Metric dashboard
- 품질/오류/비용 지표 비교
- 통계적 유의성 보조 지표

### 3) Decision workflow
- 승격/중단/롤백 버튼 + 근거 기록

## DoD
- 최소 1개 실험을 end-to-end로 실행 가능
- 실험 결과 기반 배포 결정 기록 보존

## Codex Prompt
Build chat experiment studio:
- Configure prompt/policy A-B experiments with traffic controls.
- Compare quality/error/cost metrics per variant.
- Support promote/stop/rollback decisions with audit trail.
