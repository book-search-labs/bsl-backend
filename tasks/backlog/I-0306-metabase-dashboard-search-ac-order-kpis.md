# I-0306 — Metabase/ Dashboard (Search/AC/Custom KPI)

## Goal
Create BI dashboards that allow operators to “check the list right”:
- Search Quality proxy
- Automatic Switching/CTR
- (If you are a commerce) order/paid KPI

## Why
- Grafana is strong in SLO/Tech mark, Metabase is strong in “Product KPI”
- “Operating Dashboard” in the portfolio

## Scope
### 1) Metabase connection
- ClickHouse
- User/Title: Only Admin Access (First)

### 2) Minimum KPI Dashboard (Circuit v1)
Search:
- 0-result rate
- top click rate (CTR), average position
- dwell distribution (short/long stay)
- query top N+ failed query list

Autocomplete:
- Redis hit rate + select rate
- AC select

RAG(Optional):
- Answer Satisfaction(👍), citations included rate, fallback rate

Commerce:
- cart→order→pay funnel
- refund rate

### 3) Report/Share
- Day/ week report (screenshot/link)
- Operating Note Template (Ishu→Jochi→Floor)

## Non-goals
- Comprehensive Experimental Analysis/Association Black (Extra)
- Organization/Multi-Reference Model (simplified)

## DoD
- Metabase connects to OLAP and opens the default dashboard
- Minimum 2 (Search/Autocomplete) + 1 (Chat/Commerce) Create dashboard
- “Secure Query List” is provided in a manner that can be used in operation

## Codex Prompt
Set up Metabase dashboards:
- Deploy Metabase connected to OLAP (ClickHouse/BigQuery).
- Create core KPI dashboards for Search and Autocomplete (plus optional Chat/Commerce).
- Include saved questions for failure queries and trend monitoring.
- Document how to refresh and interpret the dashboards.
