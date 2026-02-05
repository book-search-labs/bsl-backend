# A-0123 — Admin RAG Eval & Labeling UI (question sets, judgments)

## Goal
RAG 챗봇 품질을 개선하기 위한 **평가/라벨링 운영 UI**를 제공한다.
- 질문셋(Golden/Shadow/Hard) 관리
- 답변/근거(citations) 확인
- 판정(grounded/helpful/hallucination 등) 저장
- 결과 export → Offline eval/회귀 테스트에 활용

## Background
- “근거 기반” RAG는 **라벨링 루프**가 없으면 개선 속도가 급격히 떨어진다.
- 자동 평가만으로는 부족하고, 운영자가 빠르게 실패 케이스를 모아야 한다.

## Scope
### 1) Question Set Management
- Set 유형: GOLDEN / SHADOW / HARD
- 기능:
  - 생성/수정/비활성화
  - 태그/카테고리/난이도
  - 샘플링(최근 인기 질문에서 생성: 선택)

### 2) Labeling Workspace
- 질문 단위 상세 화면:
  - question (원문)
  - model answer (스트리밍 종료 결과)
  - citations 카드(문서/섹션/페이지/스니펫)
  - used_chunks/debug(선택)
- 판정 항목(최소):
  - grounded: Y/N/UNKNOWN
  - helpful: 1~5
  - hallucination_suspected: Y/N
  - missing_citation: Y/N
  - comment (텍스트)
- “다음 항목” 단축키/버튼 제공

### 3) Review & Export
- 필터: set_id, grounded, hallucination, date, judge
- Export:
  - JSONL/CSV (eval runner 입력용)
  - 최소 컬럼: question_id, question, answer, citations, judgments, created_at

## Non-goals
- RAG 파이프라인 구현(B-0282~0284)
- 자동 평가 모델 자체 개발(추후)

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
- 좌: 질문/답변, 우: citations/스니펫
- “근거 없음” 플래그는 가장 눈에 띄게(색상/아이콘)

## Security / Audit
- 판정 저장/셋 변경은 audit_log 기록(B-0227 연계)

## DoD
- 운영자가 하루에 최소 50~200개 항목을 빠르게 판정 가능
- Export 결과로 Offline eval 회귀셋을 만들 수 있음
- BFF 경유 + RBAC 적용 + audit_log 남음

## Codex Prompt
Admin(React)에서 RAG 평가/라벨링 UI를 구현하라.
Question set 목록/생성, 항목 리스트/상세, 판정 저장, 필터/Export까지 제공하라.
BFF API만 사용하고 RBAC/감사로그 전제를 따른다.
