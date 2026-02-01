# I-0318 — CI에 Offline Eval 게이트 추가 (성능 하락 배포 금지)

## Goal
검색/랭킹/모델 변경이 들어가면 CI에서 자동으로 Offline Eval을 돌려
**기준 대비 성능 하락이면 merge/배포를 차단**한다.

## Why
- “검색은 잘 되겠지”는 항상 깨짐 (인덱스/룰/모델/피처 변경의 부작용)
- 운영형 포트폴리오의 핵심은 “품질 회귀 방지” 장치

## Scope
### 1) Eval 실행 형태
- CLI 커맨드 형태로 고정:
  - `make eval` 또는 `python -m eval.run --suite golden`
- 입력:
  - golden/shadow/hard query set
  - baseline snapshot(이전 모델/정책 결과) 또는 저장된 기준 metrics
- 출력:
  - `eval_report.json` + 요약 테이블
  - 실패 사유(어떤 지표가 얼마나 떨어졌는지)

### 2) CI workflow
- PR에서:
  - lightweight: golden(샘플)만
- main/tag에서:
  - full: golden+hard + (가능하면) shadow subset
- 실패 조건(예시):
  - NDCG@10 -0.5%p 이하
  - 0-result-rate +0.2%p 이상
  - Recall@100 급락
  - latency proxy 상한 초과

### 3) 결과 저장
- model_registry/eval_run과 연계 가능(Backend 티켓과 연결)
- CI artifact로 업로드

## Non-goals
- 완전 자동 튜닝/최적 모델 선택(추후)

## DoD
- PR에서 eval이 자동 실행되고, 회귀 시 CI가 fail
- 실패 리포트가 “원인 파악 가능한 수준”으로 남음
- 최소 1회 실제 회귀 상황을 만들어 차단되는지 검증

## Codex Prompt
Add offline-eval regression gate to CI:
- Provide eval runner CLI producing eval_report.json and pass/fail based on thresholds.
- Integrate into GitHub Actions for PR and main pipelines.
- Upload reports as artifacts and print a concise summary in CI logs.
