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
