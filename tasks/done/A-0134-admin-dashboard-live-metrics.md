# A-0134 — Admin Dashboard Live Metrics

## Goal
Admin Dashboard에서 실시간 운영 지표(쿼리 수, p95/p99, zero-result, rerank 적용률 등)를 보여준다.

## Background
- Dashboard 카드가 현재 정적 숫자 (placeholder).
- 운영 판단에 필요한 지표는 실시간/최근 시간대 기준으로 제공되어야 함.

## Scope
- KPI 카드 (최근 15m/1h/24h)
  - query count, p95 latency, zero-result rate, rerank on/off 비율, error rate
- 트렌드 스파크라인 (간단한 라인 차트)
- 필터: time window 선택

## API (BFF)
> 신규 API 필요. 계약/스키마는 별도 PR에서 정의.
- `GET /admin/ops/metrics/summary?window=15m|1h|24h`
- `GET /admin/ops/metrics/timeseries?metric=...&window=...`

## DoD
- Dashboard 카드가 실제 지표로 갱신됨
- time window 변경 시 즉시 반영
- 에러/로딩 상태 UX 제공

## Codex Prompt
Admin(React)에서 Dashboard를 실시간 지표 기반으로 업데이트하라.
KPI 카드/스파크라인을 표시하고 BFF API를 호출해 데이터를 가져와 렌더링하라.
