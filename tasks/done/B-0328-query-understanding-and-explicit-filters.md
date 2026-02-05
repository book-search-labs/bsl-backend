# B-0233 — Query Service: 통합검색 Understanding(룰 기반) + 명시 필터 구문 파싱(author:/isbn:/series:)

## Goal
- QS prepare에서 통합검색 입력을 더 구조화한다:
- 명시 필터 구문: `author:`, `title:`, `isbn:`, `series:`, `publisher:`
- 결과를 QC v1.1 `understanding/entities/constraints/retrievalHints`에 반영
- SR이 필드 라우팅(ISBN exact, author boost 등)을 할 수 있게 만든다.

## Why
- “한 검색창”의 핵심은 **의도 파악 + 필드 라우팅**

## Scope
### In scope
- Query syntax 파서(MVP)
- `author:김영하`, `저자:김영하`
- `isbn:978...` (10/13, 하이픈 허용)
- 혼합: `author:김영하 데미안` → author + residual_text
- QC v1.1 반영
- entities: author/title/series/publisher/isbn
- constraints.preferredFields(논리 필드) 생성

### Out of scope
- AND/OR/NOT 등 복잡한 DSL
- LLM 기반 엔티티 추출

## Deliverables
- `services/query-service/app/core/understanding.py` (신규 권장)
- routes.py에서 QC v1.1 구성 시 understanding 반영
- 단위 테스트(파서 케이스)

## Acceptance Criteria
- [ ] `isbn:` 입력 시 isbn 중심 preferred fields 생성
- [ ] `author:` 입력 시 author entity 생성 + residual text 유지
- [ ] 파싱 실패 시 전체 free text로 fallback

## Test plan
- author only / isbn only / 혼합 케이스
