# U-0141 — 근거 UX 개선 (출처 점프/하이라이트/불일치 경고)

## Goal
답변과 근거의 연결을 UI에서 명확히 보여줘 사용자가 신뢰성을 직접 검증할 수 있게 한다.

## Why
- citations가 있어도 확인하기 어렵다면 근거 기반 UX로서 가치가 낮음

## Scope
### 1) 출처 카드 개선
- 문서/섹션/페이지 정보 명확화
- 클릭 시 상세 근거 영역으로 점프

### 2) 하이라이트
- 답변 문장과 연계된 스니펫 하이라이트
- 근거 없는 문장 강조(선택)

### 3) 불일치 경고
- answer-citation 매핑 실패 시 경고 UI 표시

## DoD
- 근거 카드 클릭 동선이 일관되게 작동
- 하이라이트로 근거 위치를 즉시 확인 가능

## Codex Prompt
Improve evidence UX in chat:
- Implement source jump and snippet highlight flows.
- Show warning when answer-to-citation mapping is weak.
