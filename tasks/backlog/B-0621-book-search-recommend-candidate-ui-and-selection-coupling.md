# B-0621 — Book Search/Recommend Candidate UX + Selection Coupling

## Priority
- P1

## Dependencies
- B-0602
- B-0607
- B-0620

## Goal
검색/추천 후보를 구조화 카드로 제공하고 selection state와 일치시켜 멀티턴 선택 정확도를 높인다.

## Why
- 후보 표시와 상태 저장이 분리되면 "2번째" 해석이 쉽게 깨짐

## Scope
### 1) Candidate card payload
- book_id, edition_id, title, author, price, stock, format
- `display_index`와 `selection_key` 포함

### 2) Selection coupling
- 카드 선택 이벤트가 `selection.selected_book/index`를 즉시 업데이트
- 더보기/필터 변경 시 candidate version 관리

### 3) UX policy
- 기본 Top3 + `더 보기`
- 모호 시 비교 질문(포맷/가격대/난이도)

## DoD
- 카드 선택 이후 참조 해석 정확도가 기준 이상으로 개선
- 후보 갱신 시 stale selection이 안전하게 무효화된다.

## Interfaces
- response `ui_hints.cards`
- selection update API/event

## Observability
- `chat_candidate_card_impression_total`
- `chat_candidate_select_total{index}`

## Test / Validation
- card->selection sync tests
- stale candidate invalidation tests
- multi-turn UX regression tests

## Codex Prompt
Couple candidate UI with selection state:
- Emit indexed candidate cards with stable selection keys.
- Update selection state on user picks and handle stale lists safely.
- Add guided compare prompts for ambiguous choices.
