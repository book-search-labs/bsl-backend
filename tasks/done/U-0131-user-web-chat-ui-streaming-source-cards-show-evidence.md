# U-0131 — Web User: Chat UI (RAG, 스트리밍 + 출처 카드 + 근거 보기)

## Goal
RAG 기반 챗봇을 “제품형” UI로 제공한다.
- 스트리밍 응답
- 출처(citations) 카드
- 근거 스니펫/하이라이트 보기
- 피드백(👍/👎, 근거부족/환각 신고)

## Why
- 단순 채팅이 아니라 “근거 기반”이 포트폴리오 임팩트의 핵심
- 품질 루프(피드백→평가→개선) 연결의 출발점

## Scope
### 1) Chat 화면
- 대화 리스트(사용자/봇)
- 입력창 + 전송(Enter/Shift+Enter)
- 스트리밍(토큰 단위) 렌더링 + 중단 버튼(optional)

### 2) Citations UI
- 답변 하단에 출처 카드 리스트:
  - 문서 제목/섹션/페이지(있다면)
  - “근거 보기” 클릭 시 스니펫/하이라이트 모달 또는 사이드패널

### 3) 디버그(개발 모드)
- debug 토글 시:
  - used_chunks, retrieval queries, scores 요약 표시(사용자 노출은 dev only)

### 4) 피드백 이벤트
- 👍/👎
- 태그: hallucination_suspected / insufficient_citation / not_helpful 등
- 코멘트(선택)

## Non-goals
- 멀티모달(이미지/파일 업로드) 1차 제외(후속)

## DoD
- 스트리밍 응답이 UX 깨짐 없이 동작
- citations가 항상 렌더링되며 “근거 보기”가 작동
- 피드백이 서버로 전송되고 UI에서 제출 완료 표시

## Interfaces
- `POST /chat` (streaming: SSE 또는 chunked response)
- `POST /chat/feedback`
- (옵션) `GET /chat/history`

## Files (예시)
- `web-user/src/pages/chat/ChatPage.tsx`
- `web-user/src/components/chat/ChatMessage.tsx`
- `web-user/src/components/chat/CitationCards.tsx`
- `web-user/src/components/chat/EvidenceModal.tsx`
- `web-user/src/api/chat.ts`

## Codex Prompt
Implement RAG Chat UI:
- Build chat page with streaming responses and citation cards.
- Add evidence modal/panel showing snippets/highlights.
- Add feedback actions (thumb up/down + tags + optional comment).
- Support dev-only debug rendering for used_chunks and retrieval metadata.
