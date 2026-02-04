# B-0240 — 문서/SSOT 정렬: 서비스 책임/README 공백/Outbox Relay·Index Writer·OLAP Loader 위치 명시

## Goal
- docs/ARCHITECTURE.md(SSOT v3)와 실제 레포 상태를 “문서 기준으로” 정렬한다.
- 특히 Codex/신규 참여자가 혼동하는 부분 제거:
  1) Search Service README가 TODO인 상태
  2) Autocomplete Redis 캐시 설명 부족
  3) outbox 이벤트 emit 책임이 실제로는 BFF에 있음(AC/SR와 차이)
  4) Outbox Relay / Index Writer / OLAP Loader 서비스가 SSOT의 “서비스 목록”에서 빠져 있음

## Scope
### In scope
- `services/search-service/README.md`:
  - hybrid(lex+vec) + fusion + rerank + degrade + enhance retry(완료되면)
- `services/autocomplete-service/README.md`:
  - Redis hot cache → OS fallback + 캐시 정책
  - 이벤트 emit이 BFF에서 수행됨을 명시(현재 구현 기준)
- `docs/ARCHITECTURE.md`:
  - Outbox Relay / Index Writer / OLAP Loader를 system map & responsibilities에 포함
  - 이벤트 책임(emit 위치)을 “현재 구현 기준”으로 정확히 기술
  - 내부 서비스 non-internet-facing 원칙 재강조

## Acceptance Criteria
- [ ] README/ARCHITECTURE/API_SURFACE 간 호출흐름이 서로 모순되지 않음
- [ ] “어디서 이벤트를 쓰는지”가 1분 안에 이해됨
