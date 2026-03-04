# B-0379 — Chat Conversation Privacy DLP + Retention Enforcement

## Priority
- P1

## Dependencies
- B-0355, B-0371, I-0344

## Goal
챗 대화에 포함된 개인정보를 실시간 탐지/마스킹하고 보존주기 정책을 강제해 개인정보 리스크를 낮춘다.

## Non-goals
- 신규 PII 탐지 모델 학습 파이프라인 구축은 범위 외
- 법무 정책 자체를 정의/변경하지 않는다

## Scope
### 1) Real-time DLP filter
- 입력/출력 텍스트의 전화번호/주소/계좌/이메일 등 PII 패턴 탐지
- 위험도에 따라 마스킹/차단/추가확인 정책 적용

### 2) Storage retention policy
- 세션/요약/증거패키지별 보존 기간 정책 강제
- 만료 데이터 자동 삭제 및 삭제 감사 로그 기록

### 3) User rights alignment
- 사용자 삭제 요청 시 대화 데이터 연계 삭제 경로 제공
- export/delete 정책과 일관성 검증

### 4) Incident handling
- PII 누출 의심 이벤트 자동 알림
- 운영자 검토 큐(A-0144) 연계

## Observability
- `chat_dlp_detected_total{pii_type,action}`
- `chat_dlp_block_total{reason}`
- `chat_retention_purge_total{data_type}`
- `chat_privacy_incident_total{severity}`

## Test / Validation
- PII 탐지 규칙 회귀 테스트
- 마스킹 누락/과탐(false positive) 평가
- 보존주기 만료 삭제 배치 테스트

## DoD
- PII 노출 사고 위험 감소
- 보존주기 미준수 데이터 자동 정리
- 개인정보 관련 감사추적 가능

## Codex Prompt
Harden chat privacy controls:
- Apply real-time DLP on chat input/output with policy-based actions.
- Enforce retention and purge for conversation artifacts.
- Integrate privacy incident signaling and auditability end-to-end.

## Implementation Update (2026-03-03, Bundle 1)
- [x] Real-time DLP filter gate 추가
  - `scripts/eval/chat_privacy_dlp_filter.py`
  - pii type/action 정규화 및 detect/mask/block/review 집계
  - unmasked violation/unknown pii type/false positive/missing reason 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_privacy_dlp_filter.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_PRIVACY_DLP_FILTER=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 2)
- [x] Retention enforcement gate 추가
  - `scripts/eval/chat_privacy_retention_enforcement.py`
  - 만료(expired)/삭제(purged)/미삭제(purge miss) 검증
  - legal hold 예외 및 hold violation 검증
  - retention policy 누락 및 purge 감사로그 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_privacy_retention_enforcement.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_PRIVACY_RETENTION_ENFORCEMENT=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 3)
- [x] User rights alignment gate 추가
  - `scripts/eval/chat_privacy_user_rights_alignment.py`
  - delete/export 요청 완료율 및 auth 정합성 검증
  - delete cascade miss / export consistency mismatch 검증
  - audit 누락 및 unknown request type 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_privacy_user_rights_alignment.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_PRIVACY_USER_RIGHTS_ALIGNMENT=1 ./scripts/test.sh`

## Implementation Update (2026-03-03, Bundle 4)
- [x] Privacy incident handling gate 추가
  - `scripts/eval/chat_privacy_incident_handling.py`
  - high severity incident alert miss / operator queue miss 검증
  - ack latency p95 / resolved ratio 검증
  - runbook link 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_privacy_incident_handling.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_PRIVACY_INCIDENT_HANDLING=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 5)
- [x] Baseline drift governance 추가 (privacy 4종 공통)
  - `scripts/eval/chat_privacy_dlp_filter.py`
  - `scripts/eval/chat_privacy_retention_enforcement.py`
  - `scripts/eval/chat_privacy_user_rights_alignment.py`
  - `scripts/eval/chat_privacy_incident_handling.py`
  - `--baseline-report` + `compare_with_baseline(...)` + `gate.baseline_failures` + `source/derived.summary` + `gate_pass` 출력 반영
- [x] baseline 회귀 테스트 추가
  - `scripts/eval/test_chat_privacy_dlp_filter.py`
  - `scripts/eval/test_chat_privacy_retention_enforcement.py`
  - `scripts/eval/test_chat_privacy_user_rights_alignment.py`
  - `scripts/eval/test_chat_privacy_incident_handling.py`
- [x] CI baseline wiring + drift env 확장
  - `scripts/test.sh` (step 92~95)
  - baseline fixture 자동 연결 + `*_DROP`, `*_INCREASE` env 반영
- [x] 운영 문서 업데이트
  - `docs/RUNBOOK.md` B-0379 섹션에 baseline 실행 예시/CI drift env 추가
