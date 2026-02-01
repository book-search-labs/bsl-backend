# I-0341 — Schema Registry 도입(선택) + 호환성 CI 검사

## Goal
이벤트 스키마를 중앙에서 관리하고,
호환성(compatibility) 검사를 CI에서 자동 수행한다.

## Why
- 이벤트는 “시간을 건너뛰어” 소비되므로, 스키마 호환성은 운영 안정성의 핵심
- DLQ/Replay가 있어도 스키마가 깨지면 재처리 자체가 불가능해짐

## Scope
### 1) Registry 선택/구성
- Avro 선택 시: Confluent Schema Registry(또는 대체)
- Protobuf 선택 시: registry를 “파일 기반 + CI 호환성 검사”로 시작해도 됨
- 환경별 endpoints/dev 구성

### 2) 호환성 규칙
- 기본: BACKWARD 또는 FULL(팀/운영 수준에 따라)
- breaking change 정의(삭제/타입 변경/필수필드 추가 등)

### 3) CI 검사
- PR에서:
  - 변경된 schema가 이전 버전과 호환되는지 체크
- 결과:
  - 호환 불가면 CI fail

### 4) 운영 문서
- schema versioning 규칙
- event producer/consumer 릴리즈 순서 가이드(consumer first 등)

## Non-goals
- 모든 서비스에 즉시 강제 적용(점진 도입 가능)

## DoD
- 선택한 registry 방식이 dev 환경에서 동작
- CI에서 schema compat 체크가 수행되고, 깨지면 fail
- 최소 3개 이벤트 타입에 대해 versioning이 적용됨

## Codex Prompt
Add schema registry & compatibility CI:
- Choose Avro+Schema Registry or Protobuf with version checks.
- Implement CI job that validates backward compatibility for changed schemas.
- Document schema evolution rules and producer/consumer rollout order.
