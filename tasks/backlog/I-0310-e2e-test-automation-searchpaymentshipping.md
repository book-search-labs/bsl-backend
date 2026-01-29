# I-0310 — E2E 테스트 자동화 (검색→장바구니→주문→결제→배송)

## Goal
핵심 사용자 플로우를 **엔드투엔드(E2E)**로 자동 검증해서
릴리즈마다 “기본 동작 보장”을 CI에서 확보한다.

## Why
- 마이크로서비스/프론트 분리에서, 기능은 “통합”에서 자주 깨짐
- 계약 테스트(B-0226)만으로는 UI/플로우 실패를 못 잡음

## Scope
### 1) 테스트 레벨
- API E2E (우선): BFF 기준으로 시나리오 실행
- UI E2E (선택): Playwright로 Web User/Admin 핵심 화면만

### 2) 필수 시나리오(v1)
Search:
- 검색 → 결과 확인 → 상세 진입

Autocomplete:
- 입력 → 추천 노출 → 선택 → 검색 반영

Commerce(준비되면):
- 장바구니 담기 → 주문 생성 → 결제(모의) → 배송 상태 변경(모의) → 주문 조회

Ops(준비되면):
- Admin 로그인 → reindex job trigger → job status 확인

### 3) 테스트 데이터/고정 seed
- 테스트 전용 사용자/상품/도서 seed
- idempotent reset(테스트 끝나면 정리)

### 4) CI 통합
- PR/merge 시 API E2E 실행
- nightly로 UI E2E 실행(선택)

## Non-goals
- 모든 케이스의 완전 커버리지(초기엔 “핵심 플로우”만)

## DoD
- E2E 테스트 스위트가 자동 실행 가능(로컬 + CI)
- 실패 시 어떤 단계에서 깨졌는지 로그/스크린샷(선택) 제공
- 테스트 데이터 seed/reset 절차 문서화
- 최소 1개의 릴리즈 게이트로 동작(merge blocking)

## Codex Prompt
Implement E2E automation:
- Add API-level E2E tests against BFF for search/autocomplete/detail (and commerce later).
- Optionally add Playwright smoke UI tests for web-user/admin.
- Ensure deterministic test data seeding and cleanup.
- Integrate with CI so failures block merges.
