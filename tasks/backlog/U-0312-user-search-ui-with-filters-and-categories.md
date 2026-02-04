# U-0120 — User Web: 통합검색 UI(필터 칩/고급검색) + KDC 카테고리 브라우징

## Goal
- 하나의 검색창 + 선택적 명시 필터(칩/고급검색)
- KDC 트리 브라우징 UX 제공

## Scope
- SearchBar + FilterChips(author/title/isbn/publisher/series/kdc)
- Advanced panel(토글)
- Category drawer/tree (BFF categories API)
- 요청: query.raw + filters(구조화)

## Acceptance Criteria
- [ ] author 칩 → 저자 중심 결과 개선 체감
- [ ] 카테고리 선택 → 결과 좁혀짐
- [ ] query syntax(author:...) 직접 입력도 동작
