# A-0135 — Admin Settings Persistence

## Goal
Admin Settings 페이지에서 입력한 기본값(예: size, timeout 등)을 저장/복원할 수 있도록 한다.

## Background
- `/settings` 페이지는 현재 입력 UI만 존재하고 저장 기능이 없음.
- 운영자가 기본값을 기억할 필요 없이 자동 복원되어야 함.

## Scope
- Settings 폼 항목 저장
  - 검색 기본 size, timeout, vector/debug 기본값 등
- 저장 방식
  - 1차: localStorage
  - (선택) 서버 저장용 API 연동

## API (Optional)
- `GET /admin/settings`
- `POST /admin/settings`

## DoD
- 새로고침 후에도 설정 값이 유지됨
- 저장 실패 시 에러 메시지 표시

## Codex Prompt
Admin(React)에서 Settings 페이지 값을 저장/복원하도록 구현하라.
기본은 localStorage를 사용하고, API가 있다면 연동 가능하도록 확장하라.
