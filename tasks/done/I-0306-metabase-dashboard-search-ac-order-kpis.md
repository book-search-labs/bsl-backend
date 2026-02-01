# I-0306 — Metabase/대시보드(검색/AC/주문 KPI)

## Goal
운영자가 “지표를 바로 확인”할 수 있는 BI 대시보드를 만든다:
- 검색 품질 proxy
- 자동완성 전환/CTR
- (커머스 있으면) 주문/결제 KPI

## Why
- Grafana는 SLO/기술지표에 강함, Metabase는 “제품 KPI”에 강함
- 포트폴리오에서 “운영 대시보드”는 설득력이 큼

## Scope
### 1) Metabase 연결
- 데이터소스: ClickHouse(또는 BigQuery)
- 사용자/권한: Admin만 접근(초기)

### 2) 최소 KPI 대시보드(초기 v1)
Search:
- 0-result rate
- top 클릭률(CTR), 평균 position
- dwell 분포(짧은/긴 체류)
- query top N + 실패 쿼리 목록

Autocomplete:
- Redis hit rate(기술지표는 Grafana) + select rate(제품지표는 Metabase)
- ac_select → search 이어짐(assist rate)

RAG(선택):
- 답변 만족(👍/👎), citations 포함 비율, fallback 비율

Commerce(선택):
- cart→order→pay funnel
- refund rate

### 3) 리포트/공유
- 일/주 단위 리포트(스크린샷/링크)
- 운영 노트 템플릿(이슈→조치→후속)

## Non-goals
- 완전한 실험분석/통계검정(추후)
- 조직/다중 권한 모델(초기엔 단순)

## DoD
- Metabase가 OLAP에 연결되고 기본 대시보드가 열림
- 최소 2개(검색/자동완성) + 선택 1개(챗/커머스) 대시보드 생성
- “실패 쿼리 리스트”가 운영에서 활용 가능한 형태로 제공됨

## Codex Prompt
Set up Metabase dashboards:
- Deploy Metabase connected to OLAP (ClickHouse/BigQuery).
- Create core KPI dashboards for Search and Autocomplete (plus optional Chat/Commerce).
- Include saved questions for failure queries and trend monitoring.
- Document how to refresh and interpret the dashboards.
