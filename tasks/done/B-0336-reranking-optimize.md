## Reranking

> > 범위: **Search Service(SR) → Ranking Service(RS) → Model Inference Service(MIS)** rerank 품질/운영 고도화  
> 목적: “지금 구조(게이팅/타임아웃/폴백)는 유지”하면서, **feature/모델/캐시/평가/데이터 루프**를 추가해 점진적으로 품질을 올린다.

---

## B-0240 — RS FeatureSpec v1 확장 (Retrieval signals + Query-Doc features)

### Goal
rerank 모델이 “학습/추론”에서 쓸 수 있게 **feature를 표준화**하고, SR→RS로 전달되는 **retrieval 신호**를 명확히 포함한다.

### Scope
- **SR → RS 요청 확장**
  - candidate에 아래 필드 포함
    - `lex_rank`, `vec_rank`, `fused_rank`(또는 `rrf_rank`)
    - `bm25_score`, `vec_score` (가능하면)
  - SR에서 위 필드가 없는 모드(예: vector off)에도 동작하도록 nullable 허용
- **RS 파생 feature 생성**
  - Query-level:
    - `query_len`, `has_number_token`, `is_isbn_like`, `has_volume_like`
  - Query-Doc match(룰 기반으로 시작):
    - `title_exact_match`, `author_exact_match`, `series_exact_match` (없으면 0)
  - Doc quality:
    - `metadata_completeness` (author/publisher/year 등 존재 여부 가중 합)
- **Feature payload 버전 추가**
  - `feature_spec_version: "rs.fs.v1"` 같은 형태로 고정 문자열

### Acceptance Criteria
- RS `debug=true`에서 **hit별 feature snapshot**이 내려온다.
- SR→RS 요청에 retrieval 신호가 포함되고, RS가 이를 feature로 반영한다.
- 기존 동작(현재 toy 모델/heuristic fallback) 깨지지 않는다.

### Notes
- 통합검색 의도 파악(저자/ISBN 라우팅) 없이도, retrieval 신호 + 간단 매칭 feature만으로도 체감 개선 가능.

---

## B-0241 — RS Score Cache 도입 (query_hash + doc_id + model)

### Goal
MIS 호출 비용/지연을 줄이기 위해 **rerank 점수 캐시**를 도입한다.

### Scope
- 캐시 키: `rerank:{model}:{query_hash}:{doc_id}`
- TTL: 5~30분 (env로 제어)
- 캐시 저장소(우선순위)
  1) Redis (권장)
  2) in-memory(Caffeine) (로컬/단일 인스턴스 옵션)
- RS 흐름
  - MIS 호출 전에 캐시 조회 → hit면 MIS 호출 스킵
  - miss면 MIS 호출 후 캐시 적재
- Metrics
  - `rs_rerank_cache_hit_total`, `rs_rerank_cache_miss_total`
  - `rs_mis_calls_total`

### Acceptance Criteria
- 동일 query 반복 시 MIS 호출 수 감소(로그/metrics 확인).
- 캐시 장애 시 **rerank는 정상 degrade(캐시 없이 진행)**.
- debug에 cache hit/miss 여부가 표시된다(선택).

---

## B-0242 — 2-Stage Rerank 오케스트레이션 추가 (RS 내부)

### Goal
현재 “toy 1-stage”에서 **2-stage rerank**로 확장 가능한 구조로 변경한다.
- Stage1: cheap scorer로 topN→topK 줄이기
- Stage2: expensive scorer(cross-encoder)로 topK 정밀 정렬

### Scope
- RS 요청 옵션 확장(Backward compatible)
  - `options.rerank.stage1.enabled` (default false)
  - `options.rerank.stage1.topK`
  - `options.rerank.stage1.model` (optional)
  - `options.rerank.stage2.enabled` (default true or existing behavior)
  - `options.rerank.stage2.topK`
  - `options.rerank.stage2.model` (optional)
  - `options.timeout_ms`는 stage별로 분배(예: 40/60)
- 실행 규칙
  - Stage1만 켜도 동작 (Stage2 off)
  - Stage2만 켜도 동작 (Stage1 off)
  - 둘 다 켜면 Stage1 결과 상위 K만 Stage2로 전달
- Degrade 정책
  - Stage2 timeout/오류 → Stage1 결과로 degrade
  - Stage1도 실패하면 기존 heuristic fallback 유지
- Debug
  - stage별 `reason_code` (skip/timeout/budget/cb 등)

### Acceptance Criteria
- Stage1-only / Stage2-only / Stage1+Stage2 조합 모두 동작.
- Stage2 timeout이면 Stage1 결과로 자동 degrade.
- debug에 stage별 스킵/실행/실패 이유가 남는다.

---

## B-0243 — MIS에 “실제 rerank 모델” 추가 (toy → baseline)

### Goal
`rerank_toy_v1` 외에 최소 1개의 “베이스라인 모델”을 추가해 품질을 올린다.

### Scope (옵션 A/B 중 최소 1개)
- **옵션 A) LTR(피처 기반) scorer**
  - 입력: RS feature vector → score
  - 초기에는 “가중합/룰”로 시작 가능(학습 전 베이스라인)
  - 추후 XGBoost/LightGBM → ONNX로 교체 가능한 인터페이스 설계
- **옵션 B) Cross-encoder reranker**
  - 입력: (query, doc_text) → score
  - `doc_text`는 title/author/publisher/year를 합친 짧은 텍스트부터 시작
- MIS model_registry에 모델 등록
  - `task: "rerank"`, `active: true|false` 지원
  - 요청 payload에서 model override 가능

### Acceptance Criteria
- model_registry에 `task=rerank`로 **toy 외 1개 모델** 등록.
- RS에서 model override로 새 모델 선택 가능.
- 새 모델 실패 시 기존 fallback(heuristic)이 유지된다.

---

## B-0244 — Rerank 품질 판단/평가 루프 만들기 (Offline Eval v1)

### Goal
“좋아졌는지/나빠졌는지”를 수치로 확인해서 rerank 개선을 반복 가능하게 만든다.

### Scope
- 평가 데이터셋 3종 구조
  - `golden`(고정)
  - `shadow`(최근 로그 샘플)
  - `hard`(오타·초성·시리즈·ISBN 등)
- 지표
  - `NDCG@10`, `MRR@10`, `Recall@100`
  - `0-result-rate proxy`(가능하면)
- 실행 형태
  - 로컬 스크립트 실행 + CI에서 smoke 수준 실행(시간 제한)
- 산출물
  - 모델/설정별 리포트 JSON + 요약 텍스트

### Acceptance Criteria
- “변경 전/후” rerank 설정 비교 리포트를 자동 생성.
- 최소 1개 지표 regression이면 CI에서 fail 가능(옵션).

---

## B-0245 — Search 이벤트 → 학습 데이터 형태로 정규화 (ClickHouse/FeatureStore용)

### Goal
rerank 학습/튜닝에 쓸 “(query, doc, label)” 형태가 나오는 이벤트 루프를 만든다.

### Scope
- outbox 이벤트 기반(현 상태에서 가능한 범위부터)
  - `search_impression`(imp_id, query_hash, results[])
  - `search_click`(있다면)
  - `dwell`(있다면)
  - `purchase`(commerce 붙이면)
- 라벨 정의(초기안)
  - impression only = 0
  - click = 1
  - dwell > 10s = 2
  - purchase = 3
- OLAP(ClickHouse)에서 join 가능한 키 설계
  - `imp_id`, `query_hash`, `doc_id`, `event_time`
- 학습 샘플 추출 쿼리/스크립트 제공

### Acceptance Criteria
- 특정 기간에 대해 학습 샘플을 뽑는 쿼리가 가능.
- query_hash 기반으로 “같은 의도” 묶어서 분석 가능.
- PII 최소화(원문 query raw 저장 정책 포함).

---

# 권장 실행 순서 (체감 빠른 루트)
1. **B-0240 FeatureSpec 확장**
2. **B-0243 MIS baseline 모델 1개 추가**
3. **B-0242 2-stage 구조**
4. **B-0241 캐시**
5. **B-0244~0245 평가/데이터 루프**
