# U-0130 — Web User: API 호출을 BFF로 전환(무중단) (BFF primary + direct fallback)

## Goal
현재 Web User가 직접 호출하던 QS/기타 API를 **BFF 단일 진입점**으로 점진 전환한다.
- 1단계: **BFF 우선 호출 + direct fallback 토글**
- 2단계: 안정화 후 direct-call 제거

## Why
- 운영형 표준(인증/레이트리밋/관측/이벤트)을 BFF에서 통제해야 함
- 프론트는 “API 변경”에 취약 → 토글 기반으로 무중단 이행 필요

## Scope
### 1) API 라우팅 레이어 추가
- `apiClient`에 라우팅 로직 추가:
  - env: `VITE_API_MODE=bff_primary|direct_primary|bff_only`
  - 우선 경로 실패 시 fallback(네트워크 오류/5xx 중심, 4xx는 fallback 금지)

### 2) 대상 엔드포인트 전환
- Search: `/search`
- Autocomplete: `/autocomplete`
- Book detail: `/books/:id`
- Chat: `/chat` (Phase 7이지만, 인터페이스는 미리 연결 가능)

### 3) 공통 헤더/추적
- `x-request-id`(클라이언트 생성 or BFF 생성 정책에 따라)
- `traceparent`(가능하면)
- 에러 로그에 request_id 포함

### 4) 관측/릴리즈 체크
- BFF 경로 vs direct 경로 비율 로깅(프론트 측)
- 에러율/latency 비교(간단 지표라도)

## Non-goals
- 인증/권한 자체 구현(이는 B-0227에서 BFF가 담당)

## DoD
- prod에서 `bff_primary`로 동작 가능
- direct fallback이 실제 장애 상황에서 정상 작동
- 안정화 후 `bff_only`로 전환 가능한 상태

## Interfaces
- BFF base: `VITE_BFF_BASE_URL`
- Direct base(임시): `VITE_DIRECT_QS_BASE_URL` 등(기존 유지)

## Files (예시)
- `web-user/src/api/client.ts` (라우팅/리트라이/에러 분류)
- `web-user/src/api/search.ts`
- `web-user/src/api/autocomplete.ts`
- `web-user/src/api/books.ts`
- `web-user/src/api/chat.ts`

## Codex Prompt
Migrate Web User API calls to BFF with zero downtime:
- Add API routing with env toggles and safe fallback logic.
- Switch search/autocomplete/book detail/chat calls to go through the router.
- Add request_id propagation and lightweight telemetry logs.
