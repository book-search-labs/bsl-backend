# B-0386 — Chat Prompt Supply-chain Integrity + Signature Verification

## Priority
- P1

## Dependencies
- A-0141, B-0371, I-0357

## Goal
프롬프트/정책 템플릿 변조를 방지하기 위해 배포 아티팩트 서명 검증과 무결성 체크를 도입한다.

## Scope
### 1) Prompt artifact signing
- 프롬프트/정책 번들에 checksum + signature 부여
- 배포 시 서명 검증 실패면 로드 차단

### 2) Integrity enforcement
- 런타임 템플릿 로딩 시 해시 검증
- 무결성 오류 시 이전 안정 버전 fallback

### 3) Key management integration
- 서명키 회전 정책
- 키 접근권한 최소화 및 감사로그

### 4) Tamper incident flow
- 변조 의심 이벤트 즉시 알림
- incident triage + 자동 격리 절차

## Observability
- `chat_prompt_signature_verify_total{result}`
- `chat_prompt_integrity_mismatch_total`
- `chat_prompt_fallback_on_integrity_total`
- `chat_prompt_signing_key_rotation_total`

## Test / Validation
- 정상/변조 아티팩트 검증 테스트
- 키 회전 후 호환성 회귀 테스트
- 무결성 실패 fallback 동작 테스트

## DoD
- 변조 프롬프트 로딩 차단 보장
- 서명/검증 파이프라인 자동화
- 무결성 이벤트의 추적/대응 체계 확보

## Codex Prompt
Secure the prompt supply chain for chat:
- Sign prompt/policy artifacts and verify signatures at deploy/runtime.
- Block tampered bundles and fall back to trusted versions.
- Integrate key rotation, audit logs, and incident signaling.

## Implementation Update (2026-03-04, Bundle 1)
- [x] Prompt signature verification guard gate 추가
  - `scripts/eval/chat_prompt_signature_verification_guard.py`
  - signature verify fail/unsigned/untrusted/checksum mismatch 검증
  - verify fail 시 deploy/load 차단(unblocked tampered=0) 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_prompt_signature_verification_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_PROMPT_SIGNATURE_VERIFICATION_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 2)
- [x] Prompt runtime integrity fallback guard gate 추가
  - `scripts/eval/chat_prompt_runtime_integrity_fallback_guard.py`
  - 런타임 무결성 mismatch 시 fallback coverage/success 및 unsafe load 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_prompt_runtime_integrity_fallback_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_PROMPT_RUNTIME_INTEGRITY_FALLBACK_GUARD=1 ./scripts/test.sh`

## Implementation Update (2026-03-04, Bundle 3)
- [x] Prompt signing key rotation guard gate 추가
  - `scripts/eval/chat_prompt_signing_key_rotation_guard.py`
  - key rotation 성공률, unauthorized access, least-privilege violation 검증
  - deprecated key sign, KMS sync 실패, audit log 누락 검증
- [x] 단위 테스트 추가
  - `scripts/eval/test_chat_prompt_signing_key_rotation_guard.py`
- [x] CI 진입점 추가
  - `RUN_CHAT_PROMPT_SIGNING_KEY_ROTATION_GUARD=1 ./scripts/test.sh`
