# Backlog Tickets

## Chatbot 고도화 (Phase 11)
- B-0350 chat 장애 재현 키트
- B-0351 /chat 요청 유효성/한도/타임아웃 표준화 (개정 v2)
- B-0352 chat degrade 정책 명시화
- B-0353 citation coverage 게이트 강화 (개정 v2)
- B-0354 다국어 질의 품질 보강
- B-0355 대화 메모리 정책 v1
- B-0356 prompt injection/jailbreak 방어 체인
- B-0357 chat 품질 지표 게이트 (개정 v2)
- B-0358 도메인 평가셋 확장
- B-0359 chat tool calling (주문/배송/환불, 개정 v3)
- B-0360 answer-citation entailment verifier
- B-0361 query decomposition + multi-hop retrieval
- B-0362 consent 기반 개인화 + 설명가능성
- B-0363 conversation state store (checkpoint/recovery, 개정 v2)
- B-0364 tool schema registry + permission policy
- B-0365 knowledge freshness pipeline
- B-0366 real-time feedback triage loop
- B-0367 chat workflow engine (multi-step commerce support)
- B-0368 source trust scoring + reliability label (개정)
- B-0369 sensitive action guard (double confirmation)
- B-0370 chat ticket integration + status follow-up
- B-0371 chat policy engine DSL (intent/risk/compliance, 개정)
- B-0372 chat tool result cache + consistency invalidation
- B-0373 adversarial evalset + Korean safety regression gate
- B-0374 reasoning budget controller (step/token/tool limits)
- B-0375 chat ticket triage classifier + SLA estimator (개정)
- B-0376 chat case evidence pack generator
- B-0377 source conflict resolution + safe abstention
- B-0378 deterministic agent replay sandbox + debug snapshots
- B-0379 chat conversation privacy DLP + retention enforcement
- B-0380 effective-date-aware policy answering (개정)
- B-0381 operator-approved correction memory
- B-0382 tool transaction fence + compensation orchestrator
- B-0383 chat output contract guard + claim verifier (개정)
- B-0384 Korean terminology + style governance engine
- B-0385 resolution knowledge ingestion from closed tickets
- B-0386 prompt supply-chain integrity + signature verification
- B-0387 chat intent calibration + confidence reliability model
- B-0388 chat cross-lingual query bridge + Korean-priority grounding
- B-0389 chat tool health score + capability routing
- B-0390 chat answer risk banding + tiered approval flow
- U-0140 chat UX 안정화
- U-0141 근거 UX 개선
- U-0142 chat quick actions UX
- U-0143 chat agent handoff + guided forms UX
- U-0144 chat transparency + reliability panel UX
- U-0145 chat incident recovery + user guidance UX
- U-0146 chat ticket lifecycle timeline + escalation UX
- U-0147 chat privacy/memory/action consent controls UX
- U-0148 chat decision explainability + denial reason UX
- U-0149 chat risk-state visualization + user-safe flow UX
- A-0140 chat ops 대시보드
- A-0141 prompt/policy 버전 운영 UI
- A-0142 chat triage workbench
- A-0143 chat experiment studio (prompt/policy A-B)
- A-0144 chat governance console (exceptions/policy review)
- A-0145 chat red-team lab + safety campaign manager
- A-0146 chat ticket ops quality + SLA command center
- A-0147 chat policy simulator + blast-radius lab
- A-0148 chat compliance evidence hub + audit export
- A-0149 chat risk ops cockpit + weekly governance review
- I-0350 LLM 비용/쿼터/속도 가드레일
- I-0351 chat 장애 런북/리허설 강화
- I-0352 chat canary/shadow/auto-rollback (개정)
- I-0353 chat SLO guardrails + auto remediation (개정 v2)
- I-0354 chat multi-LLM routing failover + cost steering (개정 v2)
- I-0355 chat priority queue + load shedding + backpressure control (개정)
- I-0356 chat synthetic journey monitoring + auto drill (개정)
- I-0357 chat control-plane backup/restore + DR drills (개정)
- I-0358 chat config drift detection + immutable release bundles (개정)
- I-0359 chat traffic partitioning + fail-safe isolation mode

## Chatbot 실서비스 전환 (Phase 12)
- B-0391 chat production launch readiness gate (실서비스 출시 게이트)
- B-0392 chat action ledger + idempotent workflow state machine
- U-0150 chat widget persistent NPC + guided commerce UX
- U-0151 chat production guided forms + recovery copy UX
- A-0150 chat go-live certification + playbook console
- A-0151 chat QA adjudication + policy approval queue
- I-0360 chat liveops on-call + release train hardening
- I-0361 chat gameday drillpack + production readiness score

## Chatbot 실서비스 확장 (Phase 13)
- B-0393 grounded answer composer + Korean policy template bundle
- U-0152 contextual entrypoints + conversion funnel UX
- A-0152 release audit + incident review console
- I-0362 data governance retention + egress guardrails

## Chatbot 실서비스 운영 고도화 (Phase 14)
- B-0394 chat session quality scorer + realtime intervention
- U-0153 chat smart sidebar + summary glance cards UX
- A-0153 chat KPI/budget/risk sign-off board
- I-0363 chat production load model + capacity forecasting

## Chatbot 실서비스 완결성 강화 (Phase 15)
- B-0395 chat resolution plan + action simulation engine
- U-0154 chat resolve center + human handoff UX
- A-0154 chat resolution ops + policy exception console
- I-0364 chat session gateway (SSE durability + backpressure)

## Chatbot 실서비스 수익/지속성 최적화 (Phase 16)
- B-0396 chat actionability scorer + repair loop
- U-0155 chat persistent conversation dock + re-entry UX
- A-0155 chat outcome review + rollback decision console
- I-0365 chat unit economics SLO + cost-to-resolve optimizer

## Chatbot 실서비스 운영 자동화 고도화 (Phase 17)
- B-0397 chat policy-aware dialog planner + escalation trigger
- U-0156 chat omnichannel handoff + notification UX
- A-0156 chat supervisor copilot + coaching loop console
- I-0366 chat policy distribution + realtime config control plane

## Chatbot 인터랙션 Agent 전환 (Phase 18, Priority Bundle)
### P0 (안전/정합성/핵심 상태)
- B-0601 chat durable state store + turn/audit ledger v1
- B-0602 chat selection memory + reference resolution v1
- B-0603 chat policy engine route decision v1
- B-0604 chat action protocol schema + idempotency v1
- B-0605 chat confirm FSM v2 for sensitive actions
- B-0608 chat eval harness (state transition regression)
- B-0611 chat authz gate v1 (tool/write)
- B-0612 chat PII redaction + retention v1
- B-0613 chat tool reliability v1 (timeout/retry/circuit breaker)
- B-0614 chat LLM budget guard + admission v1
- B-0620 book entity normalization v1

### P1 (운영/배포/선택 UX 확장)
- B-0606 chat execution claim guard + verifier v1
- B-0607 chat compose v2 (structured ui hints + guided flow)
- B-0609 chat observability v1 (reason code/trace/audit)
- B-0610 chat engine rollout (shadow/canary/auto rollback)
- B-0621 book search/recommend candidate UX + selection coupling
- B-0622 book recommendation tool pipeline (seed/candidate/explain)

### P2 (품질/성능/지속 개선)
- B-0623 chat multi-turn regression suite expansion
- B-0624 chat policy topic cache + ontology-lite
- B-0625 chat semantic cache safety guardrails v1
- B-0626 chat episode memory (consent-based retrieval) v1
- B-0627 chat recommendation experiment loop + quality gate
