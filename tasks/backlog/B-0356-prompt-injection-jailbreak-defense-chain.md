# B-0356 — Prompt injection/jailbreak 방어 체인

## Goal
챗 입력/출력 전 구간에 안전 정책을 적용해 주입 공격과 정책 우회를 줄인다.

## Why
- RAG 시스템은 외부 문서를 컨텍스트로 받기 때문에 prompt injection에 취약
- 안전성은 기능 완성보다 우선순위가 높음

## Scope
### 1) Input policy
- 위험 패턴 탐지(시스템 규칙 무시 지시, 민감정보 요청)
- 차단/경고/완화 전략 분기

### 2) Context policy
- 검색된 문서를 "명령"이 아닌 "자료"로만 해석하도록 강제
- 금지 도메인/민감 소스 필터

### 3) Output policy
- 금지 응답 유형 차단(비밀 유출, 위법 지시 등)
- 모델 출력 후 정책 재검증

### 4) 레드팀 평가
- jailbreak 프롬프트셋 정기 실행
- 차단율/오탐율 지표 추적

## DoD
- 레드팀 세트 기준 차단율 목표 달성
- 정상 질의 오탐율 기준 이내
- 차단 시 사용자 안내 메시지 + 운영 reason_code 제공

## Codex Prompt
Build prompt-injection defense chain:
- Add input/context/output policy checks around chat generation.
- Treat retrieved documents as data, not executable instructions.
- Add red-team evaluation suite and safety metrics.
