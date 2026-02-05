# U-0113 — Web User: 자동완성 UX 고도화 (Typeahead + 키보드/모바일 + 최근검색)

## Goal
검색 입력 경험을 “실서비스급”으로 끌어올린다.
- 입력 즉시 추천(autocomplete) 노출
- 키보드/모바일 완성
- 최근검색/추천쿼리로 재방문 효율 상승

## Why
- AC는 검색 전환율/CTR의 핵심 레버
- 운영루프(Kafka→집계→CTR)와 맞물려 품질이 계속 좋아짐

## Scope
### 1) UI 컴포넌트
- 공통 `SearchBox` + `TypeaheadDropdown`
- 상태: `idle / loading / showing / empty / error`
- debounce(예: 80~150ms), 최소 글자수(예: 1~2), 요청 취소(AbortController)

### 2) 키보드 내비게이션
- ↑/↓ 이동, Enter 선택, Esc 닫기
- Tab 포커스 흐름 유지
- 선택 시:
  - 검색 페이지 이동 + query 반영
  - 이벤트 발행(선택/검색은 BFF 경유로 통일될 예정)

### 3) 모바일 UX
- IME(한글 조합) 고려: compositionstart/end 처리
- 화면 작은 경우 dropdown 높이/스크롤 최적화
- “검색” 키 동작 통일

### 4) 최근검색/추천
- 최근검색(로컬스토리지 1차, 추후 서버 저장 가능)
- 최근검색 클릭 시 즉시 검색/자동완성 실행
- “지우기/전체삭제” 제공

### 5) 에러/빈 결과 처리
- 네트워크 에러: “재시도” 버튼
- 0건: “추천 없음” + 최근검색 fallback

## Non-goals
- 개인화 추천(장르/유저 취향 기반)은 Phase 8 이후

## DoD
- 헤더/검색페이지 SearchBox가 동일 컴포넌트로 동작
- 키보드/모바일에서 UX 깨짐 없이 선택/검색 가능
- 최근검색이 저장/표시/삭제 가능
- AC API 호출량이 debounce/취소로 통제됨(p95/p99 악화 없음)

## Interfaces
- 현재: QS direct-call 기준이면 `/autocomplete` 호출
- 목표: BFF 전환 후 `/autocomplete`는 BFF 단일 진입점(Phase 2)

## Files (예시)
- `web-user/src/components/search/SearchBox.tsx`
- `web-user/src/components/search/TypeaheadDropdown.tsx`
- `web-user/src/lib/recentSearch.ts`
- `web-user/src/api/autocomplete.ts`

## Codex Prompt
Implement Web User autocomplete UX:
- Build SearchBox + dropdown with debounce, abortable fetch, keyboard navigation, and mobile IME handling.
- Add recent searches in localStorage with clear actions.
- Integrate with existing search route and API client.
