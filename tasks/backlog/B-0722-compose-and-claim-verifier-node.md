# B-0722 — Compose + Claim Verifier Node

## Priority
- P2

## Dependencies
- B-0703
- B-0606
- B-0621

## Goal
응답 조합(Compose)과 실행 주장 검증(Claim Verifier)을 독립 노드로 분리해 UI 구조화와 안전성을 동시에 강화한다.

## Scope
### 1) Compose node
- `ui_hints.options/cards/forms/buttons` 생성
- route별 렌더 템플릿 적용(`OPTIONS`, `CONFIRM`, `ANSWER`)
- 채널 fallback 텍스트 자동 생성

### 2) Claim verifier node
- "조회/실행 완료" 문구에 대한 근거(sources/citations/tool_result) 검증
- confirmation 미완료 상태에서 success claim 차단
- 필요 시 안전한 복구 문구로 자동 수정

### 3) Contract-preserving mapper
- 외부 응답 스키마(`chat-response.schema.json`) 호환 유지
- optional `ui_hints` 확장 정책 문서화

### 4) Metrics
- claim block/repair 지표
- UI hint render 타입별 지표

## Test / Validation
- route-to-ui mapping tests
- claim false-positive/false-negative regression tests
- channel fallback snapshot tests

## DoD
- 구조화 응답이 주요 경로에서 기본 적용된다.
- 무근거 success claim이 차단된다.
- 계약 호환성과 UI fallback이 유지된다.

## Codex Prompt
Split response composition and claim verification into dedicated graph nodes:
- Generate structured UI hints per route.
- Block or repair unsupported success claims.
- Keep public response contract backward compatible.

---

## Implementation Update (Bundle 1)

- Extended graph runtime regression tests for compose/claim-verifier behavior:
  - success claim with citations is preserved (`status=ok`, `reason_code=OK`)
  - `CONFIRM` route emits structured button hints (`confirm`, `abort`)
  - `ANSWER` route generates card hints from `sources` when selection memory is empty
- Coverage now spans `OPTIONS/CONFIRM/ANSWER` UI-hint rendering paths and claim false-positive boundary.
