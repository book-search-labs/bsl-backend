# B-0721 — Domain Node Migration (Book/Selection/Policy Cache)

## Priority
- P2

## Dependencies
- B-0703
- B-0620
- B-0624

## Goal
도서 도메인 핵심 로직(엔티티 정규화, selection memory, 정책 토픽 캐시)을 LangGraph 노드로 완전 이식한다.

## Scope
### 1) Book entity nodes
- Book/Edition/Series/Volume/ISBN 정규화 노드 분리
- ambiguity detection 후 OPTIONS route 연결

### 2) Selection memory nodes
- `last_candidates`, `selected_book`, `selected_index` 관리 노드
- "그거/2번째/아까 추천" 참조 해소 로직 이식

### 3) Policy topic cache nodes
- `RefundPolicy/ShippingPolicy/OrderCancelPolicy/EbookRefundPolicy` 토픽 분류
- policy version 기반 캐시 무효화 노드 연결

### 4) Commerce-safe lane separation
- policy/read lane과 lookup/write lane 분리 유지
- 고위험 lane에서 semantic cache 사용 금지

## Test / Validation
- domain normalization regression tests
- multi-turn reference resolution tests
- policy cache lane safety tests

## DoD
- 도서 도메인 멀티턴 시나리오에서 legacy 대비 동등 이상 성능.
- selection 참조 오류율이 목표치 이하로 감소.
- 정책 캐시 stale 응답이 정책 버전 변경 후 노출되지 않는다.

## Codex Prompt
Migrate domain logic into LangGraph nodes:
- Port book normalization and selection memory flows.
- Preserve policy-topic cache safety and version invalidation.
- Keep lookup/write lanes isolated from low-risk caching paths.
