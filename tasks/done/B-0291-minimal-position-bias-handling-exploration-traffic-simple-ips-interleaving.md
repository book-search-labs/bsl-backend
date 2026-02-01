# B-0291 — Position Bias 최소 대응: 탐색 트래픽/간단 IPS/인터리빙 중 1개(+가드레일)

## Goal
Implicit feedback 기반 LTR 학습에서 **position bias(상단 노출 편향)**를 최소한으로 완화한다.  
MVP에서 “정답”은 아니더라도, **학습이 망가지는 수준을 막는 안전장치**를 만든다.

## Background
- 클릭은 “관련도” + “노출 순위”가 섞인 신호라 그대로 학습하면 상단만 강화되는 자기증폭이 발생.
- 실무에서는 Propensity/Interleaving/Randomization으로 편향을 줄인다.

## Options (택 1, 추천 우선순위)
### Option A (추천, 구현 난이도 낮음): **Exploration bucket (랜덤 셔플/부분 랜덤)**
- 전체 트래픽 중 1~5%를 `experiment_bucket=EXPLORE`로 지정
- TopN 후보 중 일부 구간(예: 5~20위)을 **랜덤 셔플**해서 노출
- 해당 bucket의 로그만 별도 라벨링 가중치/학습에 활용

### Option B: **간단 IPS(Propensity) 보정**
- position별 propensity p(pos)을 추정(초기엔 heuristic or 로그 기반)
- 학습 샘플에 weight = 1 / p(pos) 부여(클리핑 필수)

### Option C: **Team Draft Interleaving (A/B 비교용)**
- 기존 랭커 vs 신규 랭커 결과를 섞어 노출
- 클릭을 승패로 변환(온라인 비교에 강함)
- (MVP에서는 비용 큼 → 추후)

## Scope (v1 추천: Option A + 간단 로깅)
1) **Experiment routing**
- SR 또는 BFF에서 bucket 할당:
  - `control` / `explore`
- search_impression 이벤트에 `experiment_bucket`, `policy_version` 포함

2) **Explore 노출 정책**
- 후보 TopN에서:
  - 상위 1~4는 고정
  - 5~20 구간만 랜덤 셔플(또는 5~10만 셔플)
- DoS/품질 저하 방지:
  - “정확매칭(ISBN/완전일치)” 쿼리는 explore 제외

3) **Offline 라벨/학습에 활용**
- `B-0290` 라벨 생성 시 + `experiment_bucket` 컬럼 보존
- 학습용 데이터셋에:
  - explore bucket을 우선 사용(또는 가중치 ↑)

4) Guardrails
- explore 트래픽 비율 상한(기본 1%)
- KPI 모니터링(CTR 급락 시 자동 off)

## Non-goals
- 정교한 propensity 모델링(고급 IPS)
- 완전한 interleaving 시스템

## DoD
- explore bucket이 실제로 생성되고 로그에 남는다
- explore 노출이 적용된 SERP가 사용자에게 제공된다(1% 수준)
- 라벨 생성 결과에서 explore/control을 분리해 통계 확인 가능
- explore off 토글 가능(환경변수/feature flag)

## Codex Prompt
Implement minimal position-bias mitigation:
- Add experiment buckets (control/explore) to search requests and events.
- For explore bucket, randomize a safe slice of ranks (e.g., positions 5-20) with guardrails (exclude ISBN/exact-match queries).
- Ensure events carry experiment_bucket and can be used by label generation (B-0290).
- Add toggle to disable exploration instantly.
