# B-0365 — Knowledge Freshness Pipeline (이벤트/공지/정책 최신화)

## Priority
- P2

## Dependencies
- B-0280, B-0281

## Goal
챗봇 근거 데이터의 최신성을 보장해 "오래된 정보 답변" 비율을 줄인다.

## Scope
### 1) Source freshness tracking
- 이벤트/공지/배송정책/환불정책 문서 freshness metadata 관리
- source별 업데이트 주기 설정

### 2) Incremental sync
- 변경 감지 후 chunk 재생성/재인덱싱
- stale chunk 자동 비활성화

### 3) Freshness-aware retrieval
- 최신 문서 가중치 boost
- 만료 문서 페널티 또는 제외

### 4) Freshness monitoring
- stale answer rate
- source sync lag

## DoD
- 최신 변경 반영 지연시간(SLA) 충족
- stale answer rate 개선

## Codex Prompt
Implement chat knowledge freshness pipeline:
- Track source freshness metadata and incremental updates.
- Reindex changed chunks and down-rank stale content.
- Add freshness metrics and staleness SLA monitoring.
