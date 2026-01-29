# A-0106 — Admin Autocomplete Ops Screen (boost/ban/trends/CTR)

## Goal
Autocomplete 운영을 위한 **후보/부스팅/금칙/블랙리스트/트렌드/CTR 모니터링** 화면 제공.

## Background
- AC는 p99가 빡세고 운영 이슈(금칙어/오류/인기 급변)가 잦음.
- CTR/Popularity 집계가 붙으면 운영자가 “왜 이 후보가 뜨는지/안 뜨는지”를 봐야 함.

## Scope
### 1) Overview Dashboard
- 오늘/7일/30일:
  - `ac_impression`, `ac_select`, CTR, top prefixes, top selected queries
- 오류/지연:
  - AC p95/p99, Redis hit ratio, OS miss ratio

### 2) Candidate Explorer
- prefix 입력 → 후보 TopK 리스트
  - 후보 텍스트, score(최종), 구성요소(텍스트/CTR/popularity), source(OS/Redis)
  - last_updated, decay 적용 여부

### 3) Rules Management
- Boost rules
  - 특정 prefix/패턴에 가중치(+x)
- Ban words / blacklist
  - 금칙어(부분일치/정규식 옵션)
  - blacklist query(완전일치)

### 4) Trend Monitor
- 급상승 prefix/query (시간 창)
- 운영 조치 버튼:
  - boost 추가 / ban 추가 / 후보 pin(선택)

## Non-goals
- 집계 알고리즘 자체 구현(B-0231 범위)
- AC 서버 로직 변경(B-0214~B-0231 범위)

## Data / API
- BFF 경유(최종)
  - `GET /admin/autocomplete/metrics?window=7d`
  - `GET /admin/autocomplete/prefix/{prefix}`
  - `POST /admin/autocomplete/boost-rules`
  - `POST /admin/autocomplete/ban-words`
  - `GET /admin/autocomplete/trends?window=24h`

## UI Skeleton
- Tabs: Overview | Candidates | Rules | Trends
- Table 공통:
  - 검색/필터/정렬/페이지네이션
  - CSV export(선택)

## DoD
- 운영자가 “왜 이게 뜨지?”를 후보별 breakdown으로 확인 가능
- 금칙/부스팅 룰 CRUD 가능
- 트렌드에서 운영 조치(룰 추가)까지 2~3 클릭 이내

## Observability
- Admin 액션은 audit_log에 남는다(B-0227 연동)

## Codex Prompt
Admin(React)에서 Autocomplete Ops 화면을 구현하라.
탭(Overview/Candidates/Rules/Trends) 구조로 만들고, prefix 조회 시 후보 TopK와 score breakdown을 보여줘라.
룰 CRUD(부스팅/금칙/블랙리스트)를 제공하고 audit 로그가 남도록 BFF API를 호출하라.
