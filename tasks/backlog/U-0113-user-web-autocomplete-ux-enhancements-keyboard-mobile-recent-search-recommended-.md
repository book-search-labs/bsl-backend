# U-0113 — Web User: Advanced UX (Typeahead + Keyboard/Mobile + Recent Search)

## Goal
You can use the "Secure-Free" button.
- Input Instantly Recommended(autocomplete) Exposure
- Keyboard/Mobile Complete
- Copyright (C) 2018. All Rights Reserved.

## Why
- AC Search Conversion Rate/CTR, Core Lever
- We use cookies to improve your browsing experience. This website uses cookies to improve your browsing experience. By continuing to use this site, you consent to the use of cookies on your device as described in our 쿠키 정책.

## Scope
### 1) UI component
-  TBD   +   TBD  
- Condition:   TBD   
- debounce(e.g. 80~150ms), Minimum number of letters (e.g. 1~2), Cancel request (AbortController)

### 2) Keyboard Navigation
- ↑/↓ Move, Choose Enter, Close Esc
- Tab Focus
- Price:
  - Skip to main content
  - Event Issue (Select/Search will be unified by BFF)

### 3) Mobile UX
- IME(Hangle Combination) consideration: compositionstart/end processing
- Screen Small case dropdown height/scroll optimization
- “Search” key action unification

### 4) Recent Search/Recommended
- Copyright (c) 2015 SHINSEGAE. All Rights Reserved.
- Copyright (C) 2015. All Rights Reserved.
- Provides “Wood/Wood”

### 5) Error/bin results processing
- Network Error: “Review” button
- 0 items: "Not recommended" + recent search fallback

## Non-goals
- Personalization Recommendation (based on Zir/Yur) after Phase 8

## DoD
- Header/Searchpage SearchBox works with the same component
- Select/Search without UX Break in Keyboard/Mobile
- Copyright (C) 2018. All Rights Reserved.
- AC API calls are controlled by debounce/resolution(p95/p99 no worse)

## Interfaces
- Current: QS direct-call standard   TBD 
- Goal: BFF After Switching   TBD   BFF Single Entry Point (Phase 2)

## Files (example)
- `web-user/src/components/search/SearchBox.tsx`
- `web-user/src/components/search/TypeaheadDropdown.tsx`
- `web-user/src/lib/recentSearch.ts`
- `web-user/src/api/autocomplete.ts`

## Codex Prompt
Implement Web User autocomplete UX:
- Build SearchBox + dropdown with debounce, abortable fetch, keyboard navigation, and mobile IME handling.
- Add recent searches in localStorage with clear actions.
- Integrate with existing search route and API client.
