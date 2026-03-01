# B-0360 — Answer-Citation Entailment Verifier (2차 검증)

## Priority
- P1

## Dependencies
- B-0353

## Goal
생성된 답변을 출처 스니펫과 2차로 대조해 모순/과장 문장을 자동 검출한다.

## Why
- citation이 존재해도 문장 의미가 스니펫과 불일치할 수 있음

## Scope
### 1) Verifier 단계 추가
- 생성 후 entailment 검증(pass/fail/uncertain)
- 실패 시 답변 강등 또는 재생성

### 2) 모델/룰 전략
- 초기: 룰+lexical overlap
- 확장: NLI verifier 모델(MIS)

### 3) 실패 처리
- mismatch가 임계치 초과 시 insufficient-evidence 전환

## DoD
- verifier 도입 후 hallucination rate 개선
- mismatch 로그가 케이스 단위로 수집됨

## Codex Prompt
Add post-generation entailment verifier:
- Compare answer claims with cited snippets.
- Downgrade or regenerate when mismatch exceeds threshold.
- Log mismatch reasons for analysis.
