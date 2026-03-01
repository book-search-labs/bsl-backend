# A-0140 — Chat Ops 대시보드 (실패율/타임아웃/근거부족률/비용)

## Goal
운영자가 챗봇 이상징후를 빠르게 탐지하고 원인 범주를 식별할 수 있는 대시보드를 제공한다.

## Why
- 챗봇 장애는 원인이 다양(모델/검색/네트워크/정책)
- 지표가 분리되어 보이지 않으면 대응 지연

## Scope
### 1) 핵심 지표
- success/error/degrade rate
- stage timeout 비율
- insufficient-evidence 비율
- hallucination 신고율
- token/cost 지표

### 2) 필터
- 기간, 모델 버전, 정책 버전, locale, 사용자 세그먼트

### 3) Drill-down
- 상위 실패 reason_code
- 샘플 요청(request_id) 링크

## DoD
- 운영자가 5분 내 원인 후보를 좁힐 수 있음
- 주요 지표 이상 알람 연계 가능

## Codex Prompt
Build admin chat ops dashboard:
- Visualize reliability, groundedness, and cost metrics.
- Add drill-down by reason_code and request_id.
- Support model/policy/version filters.
