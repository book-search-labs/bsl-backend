# U-0131 — Web User: Chat UI (RAG, Streaming + Source Card + View on )

## Goal
RAG-based chatbot provides “product type” UI.
- Streaming response
- Source Card
- Snippets/Highlight View
- Feedback(👍)

## Why
- Not a simple chat, but the core of this portfolio
- Quality Loop (feedback→valuation→repair) Starting point of connection

## Scope
### 1) Chat screen
- Conversation List (user/bot)
- Input Window + Transmission(Enter/Shift+Enter)
- Streaming (token unit) Rendering + Suspension Button (optional)

### 2) Citations UI
- Source card list at the bottom of the answer:
  - Document Title/Section/Page(If)
  - "View the root" click the snippet/highlight modal or side panel

### 3) Debug (development mode)
- debug toggle:
  - used chunks, retrieval queries, scores summary (user exposure is dev only)

### 4) Feedback Events
- 👍/👎
- Tags: hallucination suspected / insufficient citation / not helpful etc.
- (Optional)

## Non-goals
- Multimodal (image/file upload) Excludes 1st (end)

## DoD
- Streaming response does not break UX
- citations are always rendered and “see the view” works
- The feedback is sent to the server and the completion of the submission in UI

## Interfaces
- New  TBD   (streaming: SSE or chunked response)
- `POST /chat/feedback`
- (Option)   TBD  

## Files (example)
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
