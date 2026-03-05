# BSL Backend Technical Series

이 디렉터리는 혼자 진행한 로컬 사이드프로젝트 기준으로 작성한 BSL 백엔드 기술 아티클(1~31편)을 담습니다.

핵심 원칙은 단순합니다.

1. 저장소 코드/스키마에서 확인된 사실만 씁니다.
2. 배포/운영 문화 서술은 제외하고, 구현과 테스트 관점만 다룹니다.
3. 추상 설명보다 상태 전이, 실패 복구, 가드레일, reason code를 우선합니다.

## Series Index

1. [01. SSOT 기준으로 백엔드 구조 고정하기](./01-ssot-culture.md)
2. [02. JSON Schema 계약 검증 게이트](./02-contract-compat-gate.md)
3. [03. Query Prepare: 정규화와 QueryContext v1.1 생성](./03-querycontext-enhance.md)
4. [04. OpenSearch 매핑 버전과 Alias 기반 전환](./04-opensearch-index-versioning.md)
5. [05. Index Writer 재색인 상태머신](./05-index-writer-state-machine.md)
6. [06. Ranking 2-Stage + Guardrail 파이프라인](./06-ranking-two-stage-guardrail.md)
7. [07. Query Enhance 알고리즘 심화](./07-query-service-enhance-deepdive.md)
8. [08. Hybrid Retrieval + Fallback + 2-Pass 재검색](./08-search-service-resilience.md)
9. [09. MIS: 모델 호출을 서비스로 분리하기](./09-mis-inference-layer.md)
10. [10. LLM Gateway: 라우팅, 비용, 인용 강제](./10-llm-gateway-routing.md)
11. [11. Chat Graph Runtime: 상태 기반 대화 오케스트레이션](./11-chat-graph-migration.md)
12. [12. Outbox Relay: Kafka 발행, DLQ, Replay](./12-outbox-kafka-dlq-replay.md)
13. [13. Commerce 상태머신: 주문/결제/환불](./13-commerce-state-machine.md)
14. [14. BFF 보안 체인: Auth, RBAC, RateLimit, Abuse](./14-security-layered-baseline.md)
15. [15. OLAP 피처 집계와 LTR 학습 데이터 구축](./15-olap-ltr-feedback-loop.md)
16. [16. 로컬 품질 회귀 게이트: Contract, Eval, Chat Matrix](./16-observability-release-gates.md)
17. [17. 개인정보 Export/Delete 스크립트](./17-privacy-automation.md)
18. [18. 기술 부채와 리팩토링 우선순위](./18-retrospective-and-next.md)
19. [19. Query Prepare 내부 파이프라인: Normalize -> Analyze -> Understanding](./19-query-prepare-normalize-understanding.md)
20. [20. Spell Candidate Generator: 사전/키보드/편집거리 후보 생성기](./20-spell-candidate-generator-deepdive.md)
21. [21. Search Fusion 정책: RRF/Weighted 전환과 예산 분할](./21-search-fusion-policy-and-budget-split.md)
22. [22. Vector Retrieval 모드 매트릭스: 임베딩, 캐시, Doc 승격](./22-vector-retrieval-mode-cache-promotion.md)
23. [23. Material Grouping: 판본/세트 페널티와 대표본 선택](./23-material-grouping-penalty-selection.md)
24. [24. Rerank 2-Stage 오케스트레이션: Heuristic + MIS](./24-rerank-two-stage-orchestration.md)
25. [25. Rerank Guardrail/Cache 계약: 상한선과 이유코드](./25-rerank-guardrails-cache-contract.md)
26. [26. LLM Gateway 심화: Citation 파서, SSE 프로토콜, 예산 차단](./26-llm-gateway-citation-sse-budget.md)
27. [27. Chat Graph 라우팅 + Confirm FSM: 실행 전 통제 계층](./27-chat-graph-routing-and-confirm-fsm.md)
28. [28. Chat Graph Shadow 비교, Canary Gate, Replay 재현](./28-chat-graph-shadow-gate-and-replay.md)
29. [29. Index Writer 로컬 재색인 생명주기: 상태 전이와 Alias 전환](./29-index-writer-local-reindex-lifecycle.md)
30. [30. Outbox Relay 심화: Envelope, Retry, DLQ, 재처리](./30-outbox-relay-dlq-replay-deepdive.md)
31. [31. Privacy 스크립트: 사용자 데이터 Export/Delete/Purge](./31-privacy-export-delete-scripts.md)

## 읽는 순서 가이드

1. 계약/스키마 기준: 01, 02
2. 검색 경로(Query -> Search -> Ranking): 03, 06, 07, 08, 09, 19, 20, 21, 22, 23, 24, 25
3. 생성형 경로(Query Chat -> LLM): 10, 11, 26, 27, 28
4. 데이터 파이프라인/색인/이벤트: 04, 05, 12, 15, 29, 30
5. 트랜잭션/보안/개인정보: 13, 14, 17, 31
6. 기술 부채와 리팩토링: 18

## 심화판 작성 기준
이번 확장판에서는 각 편에 아래 항목을 추가해 기술 밀도를 높였습니다.

1. 코드 내부 동작 순서
2. 상태 전이/가드레일/reason code
3. 환경변수 기본값과 튜닝 포인트
4. 실패 재현 시나리오와 로컬 검증 절차

즉, 개념 소개보다 “왜 그 동작이 나왔는지 추적 가능한 문서”를 목표로 구성했습니다.
