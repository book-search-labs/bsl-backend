# B-0362 — Chat 개인화 (동의 기반 + 설명 가능)

## Priority
- P2

## Dependencies
- B-0355

## Goal
사용자 동의 범위 내에서 관심사/최근 행동을 반영해 챗 추천 품질을 높인다.

## Why
- 개인화 없는 챗 추천은 일반 응답에 머물러 전환 효율이 낮음

## Scope
### 1) Consent-aware profile
- 개인화 on/off
- 최소 프로필 신호(최근 본 도서, 카테고리 선호)

### 2) 개인화 응답
- 추천/탐색 질문에만 반영
- 일반 factual 질문에는 개인화 비활성

### 3) Explainability
- "왜 이 답변/추천인지" 설명 라벨 제공

## DoD
- opt-in 사용자군에서 usefulness 개선
- opt-out 사용자 데이터 미사용 보장
- 설명 라벨이 응답 메타데이터로 노출

## Codex Prompt
Add consent-based chat personalization:
- Use lightweight profile signals only for recommendation intents.
- Respect opt-out strictly.
- Provide explainability labels for personalized outputs.
