# A-0123 — Admin RAG Eval & Labeling UI (question sets, judgments)

## Goal
RAG chat bot to improve quality **Evaluation/Labeling operation UI** About Us
- Manage Golden/Shadow/Hard
- Check the citations
- Storage of grounded/helpful/hallucination, etc.
- Results export → Offline eval/Return test

## Background
- “Registration-based” RAG is a rapid improvement rate if you don’t have a labeling loop**.
- If you have any questions, please feel free to contact us.

## Scope
### 1) Question Set Management
- Set Type: GOLDEN / SHADOW / HARD
- Feature:
  - Production/Resolution/Reactive
  - {{if compare at price min > price min}}
  - Sampling (created in recent popular questions: selection)

### 2) Labeling Workspace
- Payment Terms:
  - FAQ
  - model answer (Streeming end result)
  - citations card(Document/Section/Page/Snippet)
  - used chunks/debug(optional)
- Fixed item(min):
  - grounded: Y/N/UNKNOWN
  - helpful: 1~5
  - hallucination_suspected: Y/N
  - missing_citation: Y/N
  - (Text)
- “Next entry” hotkey/button offer

### 3) Review & Export
- Screenshots, date, date
- Export:
  - JSONL/CSV (for eval runner input)
  - Min column: question id, question, answer, citations, sentence, created at

## Non-goals
- RAG Pipeline Implementation (B-0282~0284)
- Automatic evaluation model self-development (after)

## Data / API (via BFF)
- `GET /admin/rag/eval/sets`
- `POST /admin/rag/eval/sets`
- `GET /admin/rag/eval/items?set_id=...&status=...`
- `GET /admin/rag/eval/items/{item_id}`
- `POST /admin/rag/eval/items/{item_id}/judgment`
- `GET /admin/rag/eval/export?set_id=...&format=jsonl`

## Persistence (suggested)
- rag_eval_set(set_id, type, name, tags_json, status, created_at)
- rag_eval_item(item_id, set_id, question, expected_answer(optional), created_at)
- rag_eval_judgment(judgment_id, item_id, actor_admin_id, fields_json, created_at)

## UX Notes
- Left: Question/Write, U: citations/Snippets
- “No Conversation” flag is the most noticeable (Color/Icon)

## Security / Audit
- Revision Storage/Set changes to audit log history(B-0227 link)

## DoD
- The operator can quickly determine the minimum 50~200 items per day
- Export results can create an Offline eval regression
- BFF + RBAC Application + Audit log Nam

## Codex Prompt
Implement RAG assessment/labeling UI in Admin(React).
Question set List/Produce, List/Process, Save Plan, Filter/Export.
Use BFF API only and follow the RBAC/Integrity log.
