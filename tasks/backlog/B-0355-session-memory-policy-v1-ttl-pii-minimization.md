# B-0355 — 대화 메모리 정책 v1 (세션 TTL + PII 최소화)

## Goal
챗봇이 필요한 맥락은 유지하되, 과도한 저장/개인정보 리스크 없이 세션 메모리를 운영한다.

## Why
- 맥락 저장이 없으면 대화 연속성이 깨짐
- 무제한 저장은 비용/보안/규제 리스크를 키움

## Scope
### 1) 메모리 모델
- 단기 memory window + 요약 memory 분리
- session TTL, 최대 turn 수, 최대 토큰 수 설정

### 2) PII 최소화
- 저장 전 마스킹/필터링 규칙
- 민감정보 필드 저장 금지

### 3) 메모리 품질
- 요약 품질 점검(정보 유실/왜곡)
- memory hit/miss 관측

### 4) 삭제/만료
- TTL 기반 자동 정리
- 사용자 삭제 요청 반영 경로

## DoD
- 세션 만료/유지 규칙이 문서와 실제 동작이 일치
- PII 마스킹 규칙 테스트 통과
- 메모리 사용량/효과 지표 확인 가능

## Codex Prompt
Implement chat memory policy v1:
- Add short-term + summary memory with TTL and token limits.
- Apply PII masking before persistence.
- Expose memory usage/hit metrics and expiration cleanup.
