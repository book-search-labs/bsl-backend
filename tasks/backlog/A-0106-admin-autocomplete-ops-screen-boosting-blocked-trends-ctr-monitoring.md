# A-0106 — Admin Autocomplete Ops Screen (boost/ban/trends/CTR)

## Goal
For Autocomplete Operations**Provide/Provide/Blacklist/Trend/CTR Monitoring** Screen.

## Background
- AC is frequent by p99 and operating issues (final/overflow/input).
- When the CTR/Popularity aggregates, the operator should look at “Why this candidate is floating”

## Scope
### 1) Overview Dashboard
- Today/7/30:
  - `ac_impression`, `ac_select`, CTR, top prefixes, top selected queries
- Tag:
  - AC p95/p99, Redis hit ratio, OS miss ratio

### 2) Candidate Explorer
- prefix input → candidate TopK list
  - Component text, score(final), component(text/CTR/popularity), source(OS/Redis)
  - last updated, decay applied or

### 3) Rules Management
- Boost rules
  - Specific prefix/pattern weight(+x)
- Ban words / blacklist
  - Gold Rules (Part-time / Regular Option)
  - blacklist query

### 4) Trend Monitor
- zoom prefix/query (time window)
- Operating Action Button:
  - add boost / ban add / candidate pin(optional)

## Non-goals
- Implementation of aggregate algorithm (B-0231 range)
- AC server logic changes (B-0214~B-0231 range)

## Data / API
- BFF(Final)
  - `GET /admin/autocomplete/metrics?window=7d`
  - `GET /admin/autocomplete/prefix/{prefix}`
  - `POST /admin/autocomplete/boost-rules`
  - `POST /admin/autocomplete/ban-words`
  - `GET /admin/autocomplete/trends?window=24h`

## UI Skeleton
- Tabs: Overview | Candidates | Rules | Trends
- Table Common:
  - Scots Gaelic
  - CSV export(optional)

## DoD
- Operator “Why this is floating?” can be checked by the candidate breakdown
- Gold Rules/Sending Rules CRUD Available
- Within 2~3 clicks from trend to operational action (Add rules)

## Observability
- Admin action left audit log(B-0227 Integration)

## Codex Prompt
Implement Autocomplete Ops screen in Admin(React).
Create a tab (Overview/Candidates/Rules/Trends) structure and show the topK and score breakdown for prefix query.
We provide CRUD (booting/bending/blacklist) and call BFF API for audit logs.
