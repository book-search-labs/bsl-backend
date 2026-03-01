# U-0140 — Chat UX 안정화 (재시도/중단/이어쓰기/네트워크 복구)

## Goal
챗 UI에서 네트워크 변동/스트리밍 중단 상황에서도 사용자가 대화를 안정적으로 이어갈 수 있게 한다.

## Why
- 체감 품질은 모델 정확도뿐 아니라 UI 복원력에 크게 좌우됨
- 현재 실패 시 사용자가 상태를 이해하기 어렵고 복구 동선이 약함

## Scope
### 1) 스트리밍 안정성
- 중단 버튼/재전송 버튼
- 스트림 끊김 감지 + 자동 재연결(가능 범위)

### 2) 상태 복원
- 전송 중 메시지, 마지막 응답 상태, citation 패널 상태 복원
- 새로고침 후 session 기반 대화 재개

### 3) 오류 UX
- 오류 코드별 한국어 안내 문구
- 사용자 행동 버튼(재시도/문서 보기/문의)

### 4) 접근성
- 키보드 포커스/스크린리더 친화

## DoD
- 네트워크 단절 후 재시도 시 대화 이어짐
- 스트리밍 실패 시 사용자 안내/복구 버튼 제공
- 주요 오류 플로우 E2E 테스트 추가

## Codex Prompt
Stabilize chat UX:
- Add retry/abort/resume interactions for streaming failures.
- Restore chat state across refresh and transient network issues.
- Provide clear Korean error guidance with recovery actions.
