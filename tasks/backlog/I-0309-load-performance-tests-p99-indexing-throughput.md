# I-0309 — 부하/성능 테스트 (검색 p99 + 인덱싱 throughput)

## Goal
서빙/인덱싱 경로에 대해 **재현 가능한 부하 테스트**를 구축하고,
SLO 관점의 **p95/p99, error rate, throughput**을 측정/기록한다.

## Why
- “느림/타임아웃/비용”은 운영에서 가장 자주 터짐
- 특히 Hybrid(kNN), rerank(MIS), QS 2-pass는 병목이 되기 쉬움

## Scope
### 1) 시나리오(최소 v1)
Serving:
- /search (BM25-only)
- /search (hybrid + RRF + rerank)
- /autocomplete (redis hit / miss)
- /books/:id (캐시 hit/miss)

Indexing:
- reindex job(books_doc) throughput
- ac_candidates 업데이트(집계 반영) throughput

### 2) 도구
- k6 또는 Locust (추천: k6)
- 테스트 데이터:
  - hot queries(상위 1k)
  - long-tail queries(랜덤 5k)
  - hard queries(오타/초성/권차)

### 3) 측정 지표
- latency: p50/p95/p99
- error rate: 4xx/5xx/timeout
- dependency latency: OS/MIS/QS 단계별
- 비용 proxy:
  - QS 2-pass 호출률
  - MIS 호출률(topR)
  - embedding 호출률(캐시 hit 포함)

### 4) 리포트/게이트(선택)
- `perf/results/YYYYMMDD.md`에 결과 기록
- 릴리즈 전 최소 smoke load 통과 기준 설정(선택)

## Non-goals
- 대규모 분산 환경에서의 완전한 용량 계획(초기 범위 밖)

## DoD
- k6/locust 스크립트가 repo에 포함되고 재현 가능
- 로컬/스테이징에서 10~30분 테스트 실행 가능
- 결과 리포트(표/그래프) + 병목 분석 메모 포함
- “현재 SLO 기준” 문서화(p99 목표 등)

## Codex Prompt
Add performance/load testing:
- Implement k6 (or Locust) scenarios for search/autocomplete/detail and indexing jobs.
- Collect latency percentiles, error rates, and dependency stage metrics.
- Produce a reproducible report output and document how to run it in stage.
