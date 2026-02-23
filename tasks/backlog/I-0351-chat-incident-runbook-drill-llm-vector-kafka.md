# I-0351 — Chat 장애 런북/리허설 강화 (LLM/벡터/Kafka)

## Goal
챗봇 핵심 장애 유형별 대응 런북을 만들고 정기 리허설로 복구 시간을 단축한다.

## Why
- 장애 대응은 코드보다 절차 부재로 지연되는 경우가 많음

## Scope
### 1) 장애 시나리오
- LLM provider 장애/지연
- vector index 장애/alias mismatch
- Kafka 지연으로 피드백/메트릭 적체

### 2) 런북
- 탐지 지표, 1차 조치, 우회(degrade), 복구 절차
- 검증 체크리스트 포함

### 3) 리허설
- 분기별 장애 훈련
- MTTR/재발 방지 액션 기록

## DoD
- 시나리오별 런북 문서 완성
- 최소 1회 리허설 결과와 개선 항목 기록

## Files (예시)
- `docs/RUNBOOK.md`
- `docs/ARCHITECTURE.md`

## Codex Prompt
Strengthen chat incident runbook:
- Document detection, mitigation, and recovery steps for LLM/vector/Kafka failures.
- Add rehearsal checklist and post-incident action template.
