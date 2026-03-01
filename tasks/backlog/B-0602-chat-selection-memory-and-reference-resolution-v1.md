# B-0602 — Chat Selection Memory + Reference Resolution v1

## Priority
- P0

## Dependencies
- B-0601
- B-0620

## Goal
"그거/2번째/아까 추천한" 같은 멀티턴 지시어를 안정적으로 해석해 잘못된 대상 선택을 방지한다.

## Why
- 도서 검색/추천 대화에서 참조 해석 실패는 즉시 품질 하락과 오실행 리스크로 연결됨

## Scope
### 1) Selection state
- `selection.last_candidates[]` (book_id/edition_id/isbn/index)
- `selection.selected_book`
- `selection.selected_index`

### 2) Resolver
- ordinal resolver: `2번째` -> `last_candidates[1]`
- pronoun resolver: `그거/그 책` -> `selected_book`
- unresolved 시 route를 `OPTIONS`로 강제

### 3) 옵션 응답
- 후보가 없거나 모호하면 카드 재제시 + quick reply 반환

## DoD
- `2번째`/`그거` 시나리오에서 잘못된 도서 선택률이 기준 이하로 감소
- unresolved reference는 실행 경로로 가지 않고 옵션 선택으로 회귀
- 선택 상태가 turn 간 지속된다.

## Interfaces
- chat state `selection` 필드
- composer `ui_hints.options/cards`

## Observability
- `chat_reference_resolve_total{type,result}`
- `chat_reference_unresolved_total`

## Test / Validation
- ordinal/pronoun 해석 unit tests
- candidate empty/mismatch 회귀 테스트
- multi-turn integration tests

## Codex Prompt
Implement selection memory and referential resolver:
- Persist candidates and current selection in state.
- Resolve ordinal/pronoun references deterministically.
- Route unresolved references to safe options prompts.
