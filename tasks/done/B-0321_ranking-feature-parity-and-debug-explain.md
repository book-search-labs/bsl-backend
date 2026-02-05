# B-0321 — Ranking Service: feature parity + explain/debug output

## Goal
Ranking Service의 feature 입력/파생/스토어 조회가 현재 “로컬 JSON” 중심이고
설명가능성(explain)이 제한적이다.
운영/디버그가 가능한 수준으로:
- feature spec 단일화(features.yaml) 준수 강화
- debug 응답에서 feature vector / score breakdown / reason codes 제공
- Search Service debug/Playground와 연결 가능한 형태로 만든다.

## Why
- rerank 품질 문제는 “피처/스코어/모델버전”을 보지 못하면 못 고친다.
- LTR/Offline eval로 가려면 online/offline parity가 필수다.

## Scope
### In-scope
1) feature spec 엄격화
- 존재하지 않는 feature 요청 시 처리 규칙(0/NA/에러)
- derived features 계산의 SSOT화

2) debug explain payload
- candidate마다:
  - used_features (name:value)
  - model_version
  - score
  - reason_codes
  - (가능하면) top feature contributions(모델 종류에 따라 제한)

3) replayer 입력 포맷 정리(Playground 연동)
- debug 요청을 파일로 저장/재실행 가능하도록

### Out-of-scope
- 온라인 KV 스토어 도입(별도 티켓)
- LTR 학습/배포(Phase 6)

## DoD
- debug=true일 때 응답에 feature/score/reason이 포함됨
- 기존 non-debug 응답은 사이즈/성능 영향 최소
- 최소 unit test 1개 + 문서 1개

## Files (expected)
- `services/ranking-service/src/main/java/com/bsl/ranking/service/RerankService.java`
- `services/ranking-service/src/main/java/com/bsl/ranking/features/FeatureFetcher.java`
- `services/ranking-service/src/main/resources/config/features.yaml`
- `docs/ranking/debug.md`
- tests

## Codex Prompt
- Enhance ranking-service debug/explain output and enforce feature spec parity.
- Keep backward compatibility for non-debug calls; add docs and tests.
