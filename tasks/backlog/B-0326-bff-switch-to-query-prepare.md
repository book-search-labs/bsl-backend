# B-0231 — BFF Search Flow: QS 호출을 /query-context → /query/prepare로 전환

## Goal
- BFF 검색 경로에서 QS 호출 endpoint를 **/query/prepare**로 전환한다.
- (호환) 요청에 queryContextV11이 이미 있으면 QS 호출을 스킵한다.

## Why
- Architecture v3 happy path 정렬: **BFF /v1/search → QS /query/prepare → SR**

## Scope
### In scope
- `QueryServiceClient.fetchQueryContext()` URL 변경: `/query-context` → `/query/prepare`
- trace_id/request_id propagation 유지
- QC가 없는 경우에만 QS 호출 유지

### Out of scope
- SR의 enhance retry(B-0232)
- query syntax 파싱(B-0233)

## Deliverables
- `services/bff-service/.../QueryServiceClient.java`
- (필요 시) `services/bff-service/.../SearchController.java`

## Acceptance Criteria
- [ ] BFF /search 요청 시 QS `/query/prepare` 호출 확인
- [ ] QC v1.1이 SR 요청에 포함됨
- [ ] QC가 이미 있으면 QS 호출이 생략됨

## Test plan
- BFF 단위 테스트(가능하면)
- 로컬 E2E: BFF→QS→SR 1회 검색
