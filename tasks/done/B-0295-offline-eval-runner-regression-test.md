# B-0295 — Offline Eval Runner + 회귀 게이트(배포 차단)

## Goal
검색/랭킹 파이프라인(리트리벌→퓨전→리랭크/LTR)이 바뀌어도 **품질 저하를 CI에서 감지해 배포를 막는** “회귀 테스트 러너”를 만든다.

## Why (필요한 이유)
- 인덱스 매핑/시노님/쿼리 DSL/가중치/모델 버전 변경은 쉽게 품질을 깨뜨림
- “온라인에서 깨진 뒤 알게 되는” 비용을 CI에서 선제 차단

## Scope
### 1) Eval Dataset 세트 구성(최소 3종)
- **Golden Set**: 고정(예: 300~2000 queries) — 회귀 체크용(장기 안정)
- **Shadow Set**: 최근 인기/핫쿼리(예: 5k) — 트렌드/드리프트 감지
- **Hard Set**: 오타/초성/권차/시리즈/0건 후보 — QS/SR 고도화 품질 감지

> 저장 형태: `eval_query_set`(DB) + `eval_query_item`(query, expected doc_ids optional)

### 2) Runner 실행 방식
- 입력:
  - `pipeline_config`: (fusion=RRF, rerank=LTR+CE, topN/topR, timeout budgets 등)
  - `model_version`: model_registry active or 지정 버전
- 실행:
  - Query set을 순회하며 `/internal/search?debug=true` 호출(권장: SR 직접)
  - 결과/스코어/latency/probe 로그를 저장

### 3) Metrics (필수)
- **NDCG@10**
- **MRR@10**
- **Recall@100** (retrieval 죽었는지)
- **0-result-rate**
- **Latency proxy**(stage별 p95/p99, rerank 호출율)

> qrels가 없으면:
- Golden set은 사람 라벨(초기엔 소량) 또는 “known-good doc_id(정답 1~3개)” 방식으로 시작
- Shadow/Hard는 coverage/latency/zero-rate 중심으로 게이트

### 4) Regression Gate (예시 정책)
- NDCG@10: baseline 대비 **-0.5%p 이하**면 FAIL
- 0-result-rate: baseline 대비 **+0.2%p 이상**이면 FAIL
- Recall@100: baseline 대비 **큰 하락(예: -1%p)**이면 FAIL
- p99 latency: 예산 초과율이 임계치 넘으면 FAIL

baseline은 `eval_baseline_run_id`로 고정(또는 직전 main 브랜치 run)

### 5) 결과 저장/리포팅
- `eval_run` 테이블에:
  - metrics_json, config_json, model_version, index_alias, git_sha, created_at
- 리포트 산출:
  - markdown summary + json artifact
- 실패 케이스 추출:
  - “전보다 떨어진 쿼리 TopK”를 `eval_failure_case`로 저장(옵션)

## Non-goals
- 완전 자동 라벨링(초기엔 부분 수동/정답 doc_id 기반으로 시작)
- 온라인 A/B 최종 의사결정(이건 추후 실험 시스템)

## DoD
- 로컬에서 `make eval`(또는 스크립트)로 eval runner가 실행된다
- baseline 대비 비교하여 PASS/FAIL을 반환한다(프로세스 exit code)
- eval_run이 DB에 저장되고 리포트가 생성된다
- 최소 Golden/Hard set 기준으로 실패 시나리오가 실제로 잡힌다

## Interfaces / Contracts
- SR debug 응답에 최소 포함:
  - request_id, items(doc_id, rank_score, stage scores), pipeline(meta), timings(stage_ms)
- Runner CLI:
  - `python -m eval.run --set GOLDEN --pipeline rrf_ltr_ce --model ltr_v1`

## Codex Prompt
Implement offline eval runner + regression gate:
- Define eval query sets (golden/shadow/hard) and storage format.
- Run SR searches with debug enabled, compute NDCG/MRR/Recall/zero-rate/latency metrics.
- Compare against a baseline run and fail with exit code when thresholds breach.
- Persist eval_run with metrics/config/model/index/git info and generate a markdown report.
