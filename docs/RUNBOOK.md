# Runbook (Local)

## Quick Start (Local Search)

Start core infra + seed demo data:
```bash
./scripts/local_up.sh
```

Hard reset volumes + run sample bootstrap (`V2 -> ingest -> V3+`):
```bash
./scripts/local_reset_sample_data.sh
```

Run Search Service:
```bash
cd services/search-service
./gradlew bootRun
```

Test search:
```bash
curl -s -XPOST http://localhost:18087/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"}}'
```

Optional: autocomplete (requires OpenSearch to be up):
```bash
cd services/autocomplete-service
./gradlew bootRun
curl -s "http://localhost:8081/autocomplete?q=해리&size=5"
```

For full data ingestion, see **NLK Ingestion (Local)** below.

## Chat LLM Multi-Provider Failover Ops (Local)

책봇(query-service) 다중 LLM 라우팅은 아래 환경변수로 제어합니다.

### Core routing envs
```bash
export QS_LLM_URL=http://localhost:8010
export QS_LLM_FALLBACK_URLS=http://localhost:8011,http://localhost:8012
export QS_LLM_TIMEOUT_SEC=10
export QS_LLM_PROVIDER_COOLDOWN_SEC=15
```

### Operator override / cost steering
```bash
# 강제 라우팅 (alias: primary|fallback_1|fallback_2... 또는 base URL)
export QS_LLM_FORCE_PROVIDER=fallback_1

# provider 수동 차단 (alias/url comma-separated)
export QS_LLM_PROVIDER_BLOCKLIST=primary

# health score 기반 우선순위 라우팅
export QS_LLM_HEALTH_ROUTING_ENABLED=1
export QS_LLM_HEALTH_MIN_SAMPLE=3
export QS_LLM_HEALTH_STREAK_PENALTY_STEP=0.1
export QS_LLM_HEALTH_STREAK_PENALTY_MAX=0.5

# 인텐트별 부분 정책 (REFUND/SHIPPING/ORDER/GENERAL)
export QS_LLM_PROVIDER_BY_INTENT_JSON='{"SHIPPING":"fallback_1","REFUND":"primary"}'

# 비용 스티어링(고위험 질의는 자동 bypass)
export QS_LLM_COST_STEERING_ENABLED=1
export QS_LLM_LOW_COST_PROVIDER=fallback_1
export QS_LLM_PROVIDER_COSTS_JSON='{"primary":0.30,"fallback_1":0.14,"fallback_2":0.11}'
```

### Smoke checks
```bash
# BFF chat endpoint
curl -s -XPOST http://localhost:8088/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":{"role":"user","content":"배송 상태 알려줘"},"client":{"user_id":"1","locale":"ko-KR"}}'
```

### Incident playbook
1. Primary provider 429/5xx/timeout 증가 시 `QS_LLM_FALLBACK_URLS` 경로로 자동 failover 되는지 확인한다.
2. 품질/지연 이슈 시 `QS_LLM_FORCE_PROVIDER`로 임시 우회한다.
3. 비용 경보 시 `QS_LLM_COST_STEERING_ENABLED=1`, `QS_LLM_LOW_COST_PROVIDER`를 적용한다.
4. `QS_LLM_PROVIDER_BLOCKLIST`는 부분 차단으로만 사용하고, 전체 차단 오설정 여부를 점검한다.
5. 이슈 종료 후 `QS_LLM_FORCE_PROVIDER`를 해제해 기본 정책으로 복귀한다.

### Key metrics (labels)
- `chat_provider_route_total{provider,result,mode}`
- `chat_provider_failover_total{from,to,reason,mode}`
- `chat_provider_forced_route_total{provider,reason,mode}`
- `chat_provider_intent_route_total{intent,provider,reason,mode}`
- `chat_provider_cost_steer_total{provider,reason,mode}`
- `chat_provider_health_score{provider}`
- `chat_provider_health_penalty{provider}`
- `chat_provider_cost_per_1k{provider}`
- `chat_recommend_experiment_total{variant,status}`
- `chat_recommend_quality_gate_block_total{reason}`
- `chat_recommend_experiment_auto_disable_total{reason}`
- `chat_recommend_experiment_block_rate{variant}`
- `chat_memory_opt_in_total{result,source}`
- `chat_memory_retrieval_total{result}`
- `chat_memory_delete_total{result}`

### Recommendation quality periodic report
추천 실험 품질 상태를 리포트/게이트로 점검하려면:
```bash
python3 scripts/eval/chat_recommend_eval.py \
  --metrics-url http://localhost:8001/metrics \
  --session-id u:101:default \
  --require-min-samples \
  --min-samples 20 \
  --max-block-rate 0.4 \
  --max-auto-disable-total 0 \
  --out data/eval/reports
```
품질 게이트를 강제하려면 `--gate`를 추가한다.

피드백 집계와 개선 백로그 시드 생성:
```bash
python3 scripts/chat/export_feedback_events.py \
  --since 2026-02-01T00:00:00+00:00 \
  --output evaluation/chat/feedback.jsonl

python3 scripts/chat/aggregate_feedback.py \
  --input evaluation/chat/feedback.jsonl \
  --output evaluation/chat/feedback_summary.json \
  --backlog-output evaluation/chat/feedback_backlog.json
```
위 단계를 한 번에 수행하려면:
```bash
./scripts/chat/run_recommend_quality_loop.sh
```

### Debug endpoint
운영 중 라우팅 의사결정을 빠르게 확인하려면:
```bash
curl -s -XPOST http://localhost:8001/internal/rag/explain \
  -H 'Content-Type: application/json' \
  -d '{"message":{"role":"user","content":"배송 조회"},"client":{"locale":"ko-KR"}}'
```
응답의 `llm_routing` 필드에서 `forced_blocked`, `intent_policy_selected`, `final_chain`, `provider_stats`를 확인한다.

Provider 전체 스냅샷은:
```bash
curl -s http://localhost:8001/internal/chat/providers
```
응답의 `snapshot.providers[]`에서 provider별 `cooldown`/`stats`를, `snapshot.routing.final_chain`에서 현재 우선순위를 확인한다.

추천 실험 상태 스냅샷은:
```bash
curl -s http://localhost:8001/internal/chat/recommend/experiment
```
응답의 `experiment.total/blocked/block_rate`, `auto_disabled`로 실험 상태를 즉시 확인한다.

추천 실험 상태를 수동 초기화하려면:
```bash
curl -s -X POST http://localhost:8001/internal/chat/recommend/experiment/reset \
  -H "content-type: application/json" \
  -d '{}'
```
초기화 관측은 `chat_recommend_experiment_reset_total{result}`와 `chat_recommend_experiment_reset_requests_total{result}`로 확인한다.

세션별 fallback/미해결 컨텍스트 상태는:
```bash
curl -s "http://localhost:8001/internal/chat/session/state?session_id=u:101:default"
```
응답의 `session.fallback_count`가 임계치(`fallback_escalation_threshold`) 이상이면 상담 티켓 전환(`OPEN_SUPPORT_TICKET`) 대상이다.
`session.unresolved_context.reason_message`, `session.unresolved_context.next_action`으로 사용자 안내 문구/후속 액션을 즉시 확인한다.
`session.recommended_action`, `session.recommended_message`는 임계치/직전 실패 사유를 반영한 최종 권장값이다.
운영 지표는 `chat_session_state_requests_total{result,has_unresolved}`에서 확인한다.

세션 진단 상태를 초기화하려면:
```bash
curl -s -X POST "http://localhost:8001/internal/chat/session/reset" \
  -H "content-type: application/json" \
  -d '{"session_id":"u:101:default"}'
```
운영 지표는 `chat_session_reset_requests_total{result,had_unresolved}`에서 확인한다.
또한 챗봇에서 support ticket를 성공적으로 생성/재사용하면 미해결 컨텍스트와 fallback 카운터를 자동 초기화한다 (`chat_ticket_context_reset_total`).
`/internal/chat/session/reset`은 fallback/unresolved 외에 세션 범위 티켓 컨텍스트(최근 문의번호, 티켓 생성 쿨다운 timestamp, 세션 dedup epoch)도 함께 초기화한다.
`session_id`가 `u:<user_id>:` 패턴이면 사용자 범위 최근 문의번호/쿨다운 캐시도 함께 초기화한다.
`u:<user_id>`(suffix 없음) 패턴도 동일하게 사용자 범위 캐시 초기화 대상으로 처리한다.
동일 패턴 세션 reset 시 사용자 dedup epoch도 증가시켜 사용자 범위 stale dedup 엔트리를 무효화한다.
초기화 범위 관측은 `chat_ticket_context_reset_scope_total{scope=session_only|session_and_user}`로 확인한다.
`문의 접수해줘`처럼 일반 요청만 들어오면 unresolved context가 없더라도 대화 history의 최근 사용자 이슈 문장을 자동 보강해 ticket summary로 사용한다.
history 보강 경로는 `chat_ticket_create_with_context_total{source=history}`로 관측한다.
동일 세션에서 연속으로 ticket 생성을 시도하면 `QS_CHAT_TICKET_CREATE_COOLDOWN_SEC`(기본 30초) 쿨다운이 적용되며, 응답은 `reason_code=RATE_LIMITED`, `next_action=RETRY`, `retry_after_ms`를 반환한다.
쿨다운 기준은 사용자 단위(`user_id`)로도 함께 저장되어, 동일 사용자가 세션을 바꿔도 짧은 시간 내 반복 접수를 제한한다.
쿨다운 차단 응답에는 최근 접수번호가 있으면 함께 반환되어, 사용자에게 즉시 상태 조회 경로를 안내한다.
쿨다운 차단 응답은 `POST /api/v1/support/tickets` source citation을 포함해 UI에서 근거 배지를 유지한다.
쿨다운 관측 지표는 `chat_ticket_create_rate_limited_total{result=blocked|pass|dedup_bypass}`를 사용한다.
쿨다운 차단 시 최근 접수번호 포함 여부는 `chat_ticket_create_rate_limited_context_total{has_recent_ticket=true|false}`로 구분 관측한다.
동일 문의 dedup도 사용자 범위로 동작하며 `chat_ticket_create_dedup_scope_total{scope=session|user}`로 세션 내부/교차 세션 재사용 비율을 구분해 본다.
dedup 조회 결과는 `chat_ticket_create_dedup_lookup_total{result=miss|session|user}`로 분리 관측한다.
세션 dedup과 사용자 dedup이 동시에 존재하면 `cached_at` 기준 최신 항목을 우선 선택하며, timestamp가 같으면 세션 항목을 우선 적용한다.
최근 문의번호 캐시 TTL은 `QS_CHAT_LAST_TICKET_TTL_SEC`(기본 86400초)로 조정한다.
세션 리셋 관측은 `chat_ticket_context_reset_total{reason=session_reset}`에서도 확인할 수 있다.
최근 문의번호/쿨다운의 세션 캐시는 `user_id` 소유 정보를 포함하며, 조회 시 현재 사용자와 불일치하면 무시해 교차 사용자 오염을 방지한다.
이상 징후 관측은 `chat_ticket_session_cache_owner_mismatch_total{cache=last_ticket|create_last}`로 확인한다.
티켓 상태 조회(`내 문의 상태`)는 접수번호가 없으면 최근 문의 목록(`GET /api/v1/support/tickets?limit=1`)을 자동 조회해 접수번호를 보정한다.
티켓 상태 조회가 성공하면 해당 접수번호를 최근 문의 캐시(session/user)에 동기화해 다음 조회에서 재사용한다.
최근 문의 자동 보정 소스는 `chat_ticket_status_lookup_ticket_source_total{source=query|cache|list|missing}`로 관측한다.
최근 문의 목록이 비었거나 조회 실패하면 `needs_input`으로 접수번호 입력을 안내한다.
최근 문의 목록 조회 결과는 `chat_ticket_status_recent_lookup_total{result=found|empty|error}`로 분리 관측한다.
캐시 접수번호가 stale(`not_found`)인 경우 최신 목록으로 1회 자동 복구를 시도하며 `chat_ticket_status_lookup_cache_recovery_total{result=recovered|miss|retry_failed}`로 확인한다.
티켓 상태 응답 본문에는 상태 외에 문의 유형/중요도/예상 첫 응답 시간(분)이 함께 포함되어 상담 대기 맥락을 한 번에 안내한다.
가능하면 티켓 이벤트(`/api/v1/support/tickets/{ticketId}/events`)를 함께 조회해 최근 처리 이력을 상태 응답 문구에 병기한다.
이벤트 조회 상태는 `chat_ticket_status_event_lookup_total{result=ok|empty|error}`로 관측한다.
사용자 메시지에 접수번호(`STK...`)가 포함되면 별도 키워드 없이도 티켓 상태 조회로 자동 라우팅된다.
`내 문의 내역/목록` 질의는 `GET /api/v1/support/tickets`를 호출해 최근 티켓 목록(기본 5건, 최대 20건)을 반환한다.
티켓 목록 건수 파싱은 `N건/N개`뿐 아니라 `N tickets`, `N items`도 지원한다.
티켓 목록 조회 결과는 `chat_ticket_list_total{result=ok|empty|forbidden|error}`로 분리 관측한다.

BFF 경유 점검이 필요하면 동일 기능을 아래로 호출한다:
```bash
curl -s "http://localhost:8088/chat/session/state?session_id=u:101:default"
curl -s -X POST "http://localhost:8088/chat/session/reset" \
  -H "content-type: application/json" \
  -d '{"session_id":"u:101:default"}'
curl -s "http://localhost:8088/chat/recommend/experiment" \
  -H "x-admin-id: 1"
curl -s -X POST "http://localhost:8088/chat/recommend/experiment/reset" \
  -H "x-admin-id: 1" \
  -H "content-type: application/json" \
  -d '{}'
```

## Sample Dev Bootstrap (Recommended)

For team onboarding / fresh clone, use this exact flow:
- `3)` docker compose up
- `4)` Flyway `V2__ingest_raw.sql` 까지
- `5)` sample ingest
- `6)` Flyway `V3+`

One command:
```bash
./scripts/bootstrap_sample_dev.sh
```

Hard reset + bootstrap (recommended when data looks inconsistent):
```bash
./scripts/local_reset_sample_data.sh
```

Equivalent manual commands:
```bash
docker volume create docker_mysql-data
docker volume create docker_opensearch-data
docker compose up -d mysql opensearch opensearch-dashboards

docker run --rm \
  -v "$PWD/db/migration:/flyway/sql:ro" \
  flyway/flyway:10 \
  -url='jdbc:mysql://host.docker.internal:3306/bsl?allowPublicKeyRetrieval=true&useSSL=false' \
  -user=bsl -password=bsl \
  -target=2 migrate

INSTALL_DEPS=1 RESET=1 FAST_MODE=1 NLK_INPUT_MODE=sample EMBED_PROVIDER=toy \
  ./scripts/ingest/run_ingest.sh

docker run --rm \
  -v "$PWD/db/migration:/flyway/sql:ro" \
  flyway/flyway:10 \
  -url='jdbc:mysql://host.docker.internal:3306/bsl?allowPublicKeyRetrieval=true&useSSL=false' \
  -user=bsl -password=bsl \
  migrate
```

`run_ingest.sh` syncs `nlk_raw_nodes` to `raw_node` by default when `raw_node`/`ingest_batch` tables exist.
Disable with:
```bash
RAW_NODE_SYNC=0 ./scripts/ingest/run_ingest.sh
```

`local_down.sh` removes external MySQL/OpenSearch volumes by default.
Use `KEEP_VOLUME=1 ./scripts/local_down.sh` to keep data.

`bootstrap_sample_dev.sh` also runs `db/seeds/kdc_seed_load.sql` by default, so KDC categories are available.
Disable with:
```bash
RUN_KDC_SEED=0 ./scripts/bootstrap_sample_dev.sh
```

## Database Migrations (Flyway)

Start MySQL (if not already running):
```bash
docker compose up -d mysql
```

Run Flyway (CLI installed):
```bash
flyway -url=jdbc:mysql://localhost:3306/bsl -user=bsl -password=bsl \
  -locations=filesystem:db/migration info

flyway -url=jdbc:mysql://localhost:3306/bsl -user=bsl -password=bsl \
  -locations=filesystem:db/migration migrate
```

Or use the Flyway Docker image:
```bash
docker run --rm \
  -v "$PWD/db/migration:/flyway/sql:ro" \
  flyway/flyway:10 \
  -url=jdbc:mysql://host.docker.internal:3306/bsl \
  -user=bsl -password=bsl \
  info

docker run --rm \
  -v "$PWD/db/migration:/flyway/sql:ro" \
  flyway/flyway:10 \
  -url=jdbc:mysql://host.docker.internal:3306/bsl \
  -user=bsl -password=bsl \
  migrate
```

If the DB already has tables (not managed by Flyway), baseline once before migrate:
```bash
flyway -url=jdbc:mysql://localhost:3306/bsl -user=bsl -password=bsl \
  -locations=filesystem:db/migration baseline -baselineVersion=<latest_version>
```

Notes:
- `latest_version` is the highest `V*.sql` file in `db/migration`.
- On Linux, replace `host.docker.internal` with your host IP or use `--network host`.

## Commerce Offer Backfill (Local)

When book detail shows `판매 정보 없음` for many existing materials, run offer backfill once.
This calls `GET /api/v1/materials/{materialId}/current-offer` for materials missing active offers,
and lets commerce-service auto-provision `seller/sku/offer/inventory`.

Dry run:
```bash
python3 scripts/commerce/backfill_current_offers.py --dry-run
```

Run backfill:
```bash
python3 scripts/commerce/backfill_current_offers.py --workers 12
```

Optional: process all materials again (not only missing ones):
```bash
python3 scripts/commerce/backfill_current_offers.py --all-materials --workers 12
```

## Local OpenSearch v1.1 (Full Set)

### Start / Stop
```bash
./scripts/local_up.sh
./scripts/local_down.sh
```

`local_up.sh`는 기본으로 `pg-simulator(:8090)`도 함께 올립니다.
필요 없으면 비활성화:
```bash
ENABLE_PG_SIMULATOR=0 ./scripts/local_up.sh
```

결제 웹훅 실패 자동 재시도 스케줄러는 commerce-service에서 기본 활성화됩니다.
운영/로컬 튜닝:
```bash
export PAYMENTS_WEBHOOK_RETRY_ENABLED=true
export PAYMENTS_WEBHOOK_RETRY_DELAY_MS=30000
export PAYMENTS_WEBHOOK_RETRY_INITIAL_DELAY_MS=20000
export PAYMENTS_WEBHOOK_RETRY_BATCH_SIZE=20
export PAYMENTS_WEBHOOK_RETRY_MAX_ATTEMPTS=3
export PAYMENTS_WEBHOOK_RETRY_BACKOFF_SECONDS=30
```

관측 지표(Actuator/Prometheus):
- `commerce.webhook.events.total{provider,outcome}`
- `commerce.webhook.retry.total{outcome}`
- `commerce.webhook.retry.events.total{outcome}`
- `commerce.settlement.cycles.total{outcome}`
- `commerce.settlement.lines.total{outcome}`
- `commerce.settlement.payout.total{outcome}`
- `commerce.settlement.payout.retry.total{outcome}`
- `commerce.settlement.cycle.status.total{status}`

### Payment async drill (pg-simulator)
1. web-user에서 결제 진행 후 `pg-simulator` 체크아웃 화면에서 시나리오 버튼 선택
2. 지연 웹훅(`성공 5초/10초`) 선택 시:
   - return_url로 먼저 복귀
   - `/api/v1/payments/{id}` 상태가 `PROCESSING -> CAPTURED`로 전이되는지 확인
3. 중복 웹훅(`성공 + 중복 웹훅 3회`) 선택 시:
   - 최초 1회만 상태 전이되고 나머지는 duplicate 처리되는지 확인
   - `GET /admin/payments/{paymentId}/webhook-events`에서 `process_status` 확인
4. 웹훅만 전송(`복귀 없음`) 선택 시:
   - 사용자 복귀 없이도 webhook로 결제가 확정되는지 확인
5. 실패 이벤트 수동 재처리:
   - `POST /admin/payments/webhook-events/{eventId}/retry`
   - 원본 이벤트가 webhook queue에서 `RETRIED`로 전환되는지 확인

### Settlement drill (cycle/payout/reconciliation)
1. `POST /admin/settlements/cycles`로 기간 사이클 생성
2. `POST /admin/settlements/cycles/{cycleId}/payouts` 실행
3. 실패 건 재시도:
   - `GET /admin/settlements/payouts?status=FAILED`
   - `POST /admin/settlements/payouts/{payoutId}/retry`
4. 원장 불일치 확인:
   - `GET /admin/settlements/reconciliation?from=YYYY-MM-DD&to=YYYY-MM-DD`
   - `payment_amount` vs `sale_amount` 및 `ledger_entry_count` 확인

Skip demo seed when you only want ingest-based data:
```bash
SEED_DEMO_DATA=0 ./scripts/local_up.sh
```

### Health + aliases
```bash
curl http://localhost:9200
curl -s http://localhost:9200/_cat/aliases?v
```

### v2.1 mapping prerequisites
- OpenSearch plugins: `analysis-nori`, `analysis-icu`
- Required files (mounted by `compose.yaml`):  
  `infra/opensearch/analysis/userdict_ko.txt`  
  `infra/opensearch/analysis/synonyms_ko.txt`  
  `infra/opensearch/analysis/synonyms_en.txt`
- books_doc mapping: `infra/opensearch/books_doc_v2_1.mapping.json`

Verify plugins:
```bash
curl -s http://localhost:9200/_cat/plugins?v | rg 'analysis-(nori|icu)'
```

### If bootstrap alias update returns 404
The alias cleanup in `scripts/os_bootstrap_indices_v1_1.sh` removes aliases by index pattern
(`books_doc_v1_*`, `books_vec_v*`, etc.). If an alias currently points to an index outside those
patterns, OpenSearch returns 404.

Fix by inspecting aliases and removing the offending alias with the **actual index name**, then rerun:
```bash
curl -s http://localhost:9200/_cat/aliases?v
curl -XPOST http://localhost:9200/_aliases -H 'Content-Type: application/json' -d '{
  "actions":[{"remove":{"index":"<actual_index_name>","alias":"books_doc_read"}}]
}'
OS_URL=http://localhost:9200 scripts/os_bootstrap_indices_v1_1.sh
```

### Smoke checks
```bash
curl -s -XPOST http://localhost:9200/ac_candidates_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"text":"해"}},"size":5}'
curl -s -XPOST http://localhost:9200/authors_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name_ko":"롤링"}},"size":5}'
curl -s -XPOST http://localhost:9200/series_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"name":"해리"}},"size":5}'
```

### Optional entity indices (authors/series)
- Skip entity indices:
  ```bash
  ENABLE_ENTITY_INDICES=0 ./scripts/local_up.sh
  ```
- Authors fallback mapping:
  `infra/opensearch/authors_doc_v1.local.mapping.json`

---

## Local OpenSearch v1.1 (Books Doc/Vec)

### Start / Stop
```bash
./scripts/local_up.sh
./scripts/local_down.sh
```

### Health + aliases
```bash
curl http://localhost:9200
curl -s http://localhost:9200/_cat/aliases?v
```

### Smoke checks
```bash
curl -s -XPOST http://localhost:9200/books_doc_read/_search -H 'Content-Type: application/json' -d '{"query":{"match":{"title_ko":"해리"}},"size":3}'
curl -s -XPOST http://localhost:9200/books_vec_read/_search -H 'Content-Type: application/json' -d "{\"size\":3,\"query\":{\"knn\":{\"embedding\":{\"vector\":$(python3 -c 'import hashlib,random,json; seed=int(hashlib.sha256(b"b1").hexdigest()[:8],16); r=random.Random(seed); print(json.dumps([round(r.random(),6) for _ in range(384)]))'),\"k\":3}}}}"
```

### Safe books_doc v2 -> v2.1 migration (reading fallback split)
When moving existing `books_doc_v2_*` documents into v2.1 index, run:
```bash
OS_URL=http://localhost:9200 \
SRC_INDEX=books_doc_v2_20260228_001 \
DST_INDEX=books_doc_v2_1_20260301_001 \
CUTOVER_ALIASES=1 \
./scripts/os_reindex_books_doc_v2_to_v2_1.sh
```

This script guarantees:
- `is_hidden` missing values are backfilled to `false`
- `author_names_ko/author_names_en` are flattened from `authors`
- alias cutover happens only after validation (`missing is_hidden docs: 0`)

Legacy migration from `books_doc_v1_*` to `books_doc_v2_*` is still available via:
`./scripts/os_reindex_books_doc_v1_to_v2.sh`

### P1 reading split smoke check
Run this after v2.1 cutover:
```bash
OS_URL=http://localhost:9200 INDEX_ALIAS=books_doc_read \
  ./scripts/os_queries/check_books_doc_v2_1_reading_split.sh
```

---

## NLK Ingestion (Local)

### Data paths
- Data root: `./data/nlk` (override with `NLK_DATA_DIR=/path/to/nlk`)
- Raw files: `./data/nlk/raw`
- Checkpoints: `./data/nlk/checkpoints` (deadletters in `./data/nlk/deadletter`)
- Input mode: `NLK_INPUT_MODE=sample|full|all` (default: `sample`)

### Start stack + install deps
```bash
./scripts/local_up.sh
python3 -m pip install -r scripts/ingest/requirements.txt
```

### Run ingestion
```bash
./scripts/ingest/run_ingest.sh
./scripts/ingest/run_ingest_mysql.sh
./scripts/ingest/run_ingest_opensearch.sh
```

OpenSearch ingest defaults to `EMBED_PROVIDER=mis` and **requires** `MIS_URL`:
```bash
EMBED_PROVIDER=mis MIS_URL=http://localhost:8005 \
  ./scripts/ingest/run_ingest_opensearch.sh
```
Use `multilingual-e5-small` explicitly:
```bash
EMBED_PROVIDER=mis MIS_URL=http://localhost:8005 EMBED_MODEL=multilingual-e5-small \
  ./scripts/ingest/run_ingest_opensearch.sh
```
When `NLK_INPUT_MODE=sample` and neither `EMBED_PROVIDER` nor `MIS_URL` is set,
`run_ingest.sh` automatically falls back to `EMBED_PROVIDER=toy`.
If you don’t want embeddings:
```bash
ENABLE_VECTOR_INDEX=0 ./scripts/ingest/run_ingest_opensearch.sh
```
Or use toy embeddings without MIS:
```bash
EMBED_PROVIDER=toy ./scripts/ingest/run_ingest_opensearch.sh
```

OpenSearch ingest now writes:
- `books_doc_write` (BM25)
- `books_vec_write` (vector embeddings; required for hybrid search)
- `ac_candidates_write` (autocomplete)
- `authors_doc_write` (optional, when enabled)

### Common overrides
```bash
RESET=1 ./scripts/ingest/run_ingest.sh
INGEST_TARGETS=mysql ./scripts/ingest/run_ingest.sh
INGEST_TARGETS=opensearch ./scripts/ingest/run_ingest.sh
FAST_MODE=1 ./scripts/ingest/run_ingest.sh
NLK_INPUT_MODE=full ./scripts/ingest/run_ingest.sh
ENABLE_VECTOR_INDEX=0 ./scripts/ingest/run_ingest_opensearch.sh
```

Notes:
- Fast mode also uses `RAW_HASH_MODE=record_id` and `STORE_BIBLIO_RAW=0` unless overridden.
- `run_ingest_mysql.sh` defaults to `FAST_MODE=1` (override with `FAST_MODE=0`).
- Fast mode enables bulk MySQL loads (`MYSQL_BULK_MODE=1`) unless overridden.
- Bulk load:
  ```bash
  MYSQL_BULK_MODE=1 MYSQL_LOAD_BATCH=100000 ./scripts/ingest/run_ingest_mysql.sh
  ```
- MySQL must allow `local_infile=1` (enabled in docker-compose; restart MySQL after changes).
- If you see error 1229 about `local_infile`, it's a GLOBAL-only server variable; ensure the server config has `local_infile=1`.
- Tune MySQL batch: `MYSQL_CHUNK_SIZE=100` (reduce if MySQL disconnects).
- If MySQL crashes (InnoDB assertion), reset the local volume:
  ```bash
  ./scripts/local_down.sh
  ./scripts/local_up.sh
  ```

### Quick verification
```bash
mysql -h 127.0.0.1 -u bsl -pbsl bsl -e "SELECT COUNT(*) FROM nlk_raw_nodes;"
mysql -h 127.0.0.1 -u bsl -pbsl bsl -e "SELECT COUNT(*) FROM nlk_biblio_docs;"
curl -s http://localhost:9200/_cat/aliases?v | grep books_doc
curl -s -XPOST http://localhost:9200/books_doc_read/_search -H 'Content-Type: application/json' -d '{"size":3,"query":{"match_all":{}}}'
```

---

## Autocomplete Ops Loop (Local)

```bash
python3 -m pip install -r scripts/autocomplete/requirements.txt
python3 scripts/autocomplete/aggregate_events.py
```

Defaults:
- OpenSearch alias: `AC_ALIAS=ac_candidates_write`
- Redis cache keys: `AUTOCOMPLETE_CACHE_KEY_PREFIX=ac:prefix:`
- Decay half-life: `AC_DECAY_HALF_LIFE_SEC=604800`

If Redis is not available, cache invalidation is skipped.

---

## Kafka + Outbox Relay (Local)

### Start Kafka (Redpanda single-node)
```bash
docker compose --profile data up -d redpanda
```

Alternate (standalone):
```bash
docker run -d --name bsl-kafka -p 9092:9092 -p 9644:9644 redpandadata/redpanda:latest redpanda start --overprovisioned --smp 1 --memory 1G --reserve-memory 0M --node-id 0 --check=false --advertise-kafka-addr localhost:9092
```

### Run relay
```bash
export SPRING_PROFILES_ACTIVE=dev
export SPRING_CONFIG_ADDITIONAL_LOCATION=../../config/spring/outbox-relay/
cd services/outbox-relay-service
./gradlew bootRun
```

Ensure BFF outbox is enabled when emitting events:
```bash
BFF_OUTBOX_ENABLED=true
```

Checks:
```bash
curl -s http://localhost:8095/health
curl -s http://localhost:8095/metrics
```

Replay failed outbox events:
```bash
python3 -m pip install -r scripts/outbox/requirements.txt
python3 scripts/outbox/replay_outbox.py --status FAILED --limit 500
```

---

## OLAP (ClickHouse) + Loader (Local)

### Start ClickHouse
```bash
docker compose --profile data up -d clickhouse
```

### Run OLAP loader (Kafka → ClickHouse)
```bash
cd services/olap-loader-service
./gradlew bootRun
```

### LTR pipeline
Generate labels:
```bash
python scripts/olap/generate_ltr_labels.py --start-date 2026-01-30 --end-date 2026-01-31
```

Aggregate features:
```bash
python scripts/olap/aggregate_features.py --start-date 2026-01-30 --end-date 2026-01-31
```

Build training dataset (point-in-time join):
```bash
python scripts/olap/build_training_dataset.py --start-date 2026-01-30 --end-date 2026-01-31 --output /tmp/ltr.jsonl
```

Train LTR + export ONNX:
```bash
python3 -m pip install lightgbm onnxmltools pyyaml
python scripts/ltr/train_lambdamart.py --data /tmp/ltr.jsonl --output-dir var/models
```

Register model artifact:
```bash
python scripts/ltr/register_model.py --model-id ltr_lambdamart_v1 --artifact-uri local://models/ltr_lambdamart_v1.onnx --activate
```

Offline eval regression gate:
```bash
python scripts/eval/run_eval.py --run evaluation/runs/sample_run.jsonl --baseline evaluation/baseline.json --gate
```

---

## RAG Docs (Indexing)

Create RAG indices (OpenSearch):
```bash
DOCS_DOC_INDEX=docs_doc_v1_20260131_001 DOCS_VEC_INDEX=docs_vec_v2_20260228_001 ./scripts/os_bootstrap_indices_v1_1.sh
```

Build chunks + embeddings:
```bash
python scripts/rag/build_doc_chunks.py --input-dir data/rag/docs
python scripts/rag/embed_chunks.py --input var/rag/docs_embed.jsonl --output var/rag/docs_vec.jsonl
```

Index into OpenSearch:
```bash
python scripts/rag/index_chunks.py --docs var/rag/docs_doc.jsonl --vec var/rag/docs_vec.jsonl --deletes var/rag/docs_deletes.jsonl
```

---

## Local LLM (Ollama)
```bash
make local-llm-up
curl -fsS http://localhost:11434/v1/models
```

Model (default in `Makefile`):
- `llama3.1:8b-instruct` (override with `LOCAL_LLM_MODEL=...`)

---

## LLM Gateway (Local)
```bash
cd services/llm-gateway-service
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Example env (OpenAI-compatible local LLM):
```bash
export LLM_PROVIDER=openai_compat
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_API_KEY=
export LLM_MODEL=llama3.1:8b-instruct
export LLM_TIMEOUT_MS=15000
export LLM_MAX_TOKENS=512
export LLM_TEMPERATURE=0.2
```

QS env (optional model label pass-through):
```bash
export QS_LLM_URL=http://localhost:8010
export QS_LLM_MODEL=llama3.1:8b-instruct
```

---

## Chat smoke test (BFF → QS → LLMGW)
```bash
./scripts/smoke_chat.sh
```

---

## Search Service (Local)
```bash
./scripts/local_up.sh
cd services/search-service
./gradlew bootRun
```

Tests:
```bash
curl -s -XPOST http://localhost:18087/search -H 'Content-Type: application/json' -d '{"query":{"raw":"해리"}}'
curl -s http://localhost:18087/books/b1
```

---

## Ranking Service (Local)
```bash
cd services/ranking-service
./gradlew bootRun
```

Test rerank:
```bash
curl -s -XPOST http://localhost:8082/rerank -H 'Content-Type: application/json' -d '{"query":{"text":"해리"},"candidates":[{"doc_id":"b1","features":{"rrf_score":0.167,"lex_rank":1,"vec_rank":2,"issued_year":1999,"volume":1,"edition_labels":["recover"]}}],"options":{"size":10}}'
```

---

# Phase 9 — Observability & Operations (Production)

## Observability stack (local)
```bash
./scripts/observability_up.sh
# Grafana: http://localhost:3000
# Prometheus: http://localhost:9090
# Tempo: http://localhost:3200
# Loki: http://localhost:3100
# Metabase: http://localhost:3001
```

Stop:
```bash
./scripts/observability_down.sh
```

## MySQL backup / restore
Backup:
```bash
./scripts/mysql_backup.sh
```

Restore (from a backup file):
```bash
./scripts/mysql_restore.sh /path/to/backup.sql.gz
```

## OpenSearch snapshot / restore
Register snapshot repo + snapshot:
```bash
./scripts/opensearch_snapshot.sh
```

Restore a snapshot:
```bash
./scripts/opensearch_restore.sh SNAPSHOT_NAME
```

Retention cleanup (delete snapshots older than N days):
```bash
SNAPSHOT_RETENTION_DAYS=7 ./scripts/opensearch_snapshot_retention.sh
```

## Chat retention cleanup (state/turn/audit)
Dry-run (count only):
```bash
QS_CHAT_STATE_DB_ENABLED=true \
python3 ./scripts/privacy/purge_chat_retention.py --dry-run
```

Apply delete batch:
```bash
QS_CHAT_STATE_DB_ENABLED=true \
QS_CHAT_SESSION_STATE_RETENTION_DAYS=30 \
QS_CHAT_TURN_EVENT_RETENTION_DAYS=30 \
QS_CHAT_ACTION_AUDIT_RETENTION_DAYS=90 \
QS_CHAT_RETENTION_DELETE_BATCH_SIZE=1000 \
python3 ./scripts/privacy/purge_chat_retention.py
```

## DR rehearsal (minimum)
1) Take a **MySQL** backup + **OpenSearch** snapshot.
2) Spin up a clean environment.
3) Restore MySQL + OpenSearch.
4) Run smoke tests (search + checkout flow).
5) Document recovery time + gaps.

## Incident response (on-call)
- **SEV1:** system down, data loss risk → page immediately, rollback or failover.
- **SEV2:** partial outage, high error rate → mitigate within 30–60 min.
- **SEV3:** degraded performance, non-critical impact → fix in next business day.

### Standard procedure
1) Triage: validate alert + scope blast radius
2) Mitigate: rollback, disable feature flag, scale resources
3) Communicate: status update to stakeholders
4) Diagnose: root cause + remediation
5) Postmortem: action items + owners

## Release check (prod)
- Health checks green (BFF + Search + Autocomplete + Commerce)
- p95/p99 latency within SLO
- Error rate < 1%
- DB + OpenSearch disk < 80%

## Admin risky-action approval (optional)
If enabled (`SECURITY_ADMIN_APPROVAL_ENABLED=true`), risky admin paths require `x-approval-id`.
Create approval via SQL (example):
```sql
INSERT INTO admin_action_approval (requested_by_admin_id, action, status, approved_by_admin_id)
VALUES (1, 'POST /admin/ops/reindex-jobs/start', 'APPROVED', 2);
```
Then call the API with `x-approval-id` set to the row id.

---

# Phase 10 — Hardening (Optional)
