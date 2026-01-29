# I-0343 — Rate-limit/abuse pattern detection (bot/scraper) + blocking policy

## Goal
Detects and blocks costs/performance deterioration due to bots/scraping/conversion calls.
- “Search/Autocomplete/Chat” is very vulnerable to abuse

## Why
- Search API is easy to be a data collection target
- Chat (LLM) can be a cost bomb

## Scope
### 1) Detection Signal Collection
- IP / user_id / api_key / user-agent / path
- req/sec
- headless UA/Vin UA/Short call in session

### 2) Lockout Policy
- Price:
  1) soft limit(429 + Retry-After)
  2) Challenge (simplified token/description)
  3) hard block
- Privacy Policy by endpoint:
  - /autocomplete: short window strong limit
  - /search: Middle
  - /chat: The strongest (customer budget)

### 3) Operation tools/logs
- audit log/abuse log
- Search top offenders in Admin (validity ticket)

## Non-goals
- CAPTCHA: Please select the Star Send Email

## DoD
- Detecting/blocking minimum 3 abuse patterns
- rate-limit policy is documented and operators can be adjusted
- Unblock/delete logs are left, and consequently limited traffic impact

## Codex Prompt
Implement abuse detection & blocking:
- Collect request features and compute basic abuse heuristics.
- Enforce tiered rate-limit/block policies per endpoint.
- Record abuse actions in logs/audit and add minimal admin visibility.
