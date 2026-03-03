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

## Chat contract compatibility gate (B-0701)
```bash
python scripts/eval/chat_contract_compat_eval.py \
  --cases-json services/query-service/tests/fixtures/chat_contract_compat_v1.json \
  --contracts-root . \
  --require-all \
  --gate
```
`RUN_CHAT_CONTRACT_COMPAT_EVAL=1 ./scripts/test.sh`로 옵션 게이트를 활성화할 수 있다.

## Chat graph state schema v1 (B-0702)
- state contract: `services/query-service/app/core/chat_graph/state.py`
- validator entrypoint: `validate_chat_graph_state(..., stage=\"...\")`
- legacy adapter:
  - `legacy_session_snapshot_to_graph_state(...)`
  - `graph_state_to_legacy_session_snapshot(...)`

## Chat graph runtime skeleton (B-0703)
- runtime entrypoint: `services/query-service/app/core/chat_graph/runtime.py`
- node flow: `load_state -> understand -> policy_decide -> execute -> compose -> verify -> persist`
- engine switch:
  - `QS_CHAT_ENGINE_MODE=legacy` (default)
  - `QS_CHAT_ENGINE_MODE=shadow|canary|agent`

## Chat confirm interrupt/resume FSM (B-0704)
- FSM module: `services/query-service/app/core/chat_graph/confirm_fsm.py`
- states: `INIT -> AWAITING_CONFIRMATION -> CONFIRMED -> EXECUTING -> EXECUTED`
- exceptional states: `EXPIRED`, `ABORTED`, `FAILED_RETRYABLE`, `FAILED_FINAL`
- audit store: cache key `chat:graph:action-audit:{session_id}`

## Chat pre-node AuthZ/Action fence (B-0705)
- AuthZ gate module: `services/query-service/app/core/chat_graph/authz_gate.py`
- runtime node: `authz_gate` (`policy_decide` 직후 실행)
- required client fields for sensitive path: `user_id`, `tenant_id`, `auth_context.scopes` (`chat:write`)
- authz audit store: cache key `chat:graph:authz-audit:{session_id}`

## Chat checkpoint/replay kit (B-0706)
- replay store: `services/query-service/app/core/chat_graph/replay_store.py`
- run dir env: `QS_CHAT_GRAPH_REPLAY_DIR` (default `var/chat_graph/replay`)
- replay script:
```bash
python scripts/eval/chat_graph_replay.py --run-id <run_id>
```

## LangSmith trace integration (PII-safe, B-0711)
- adapter module: `services/query-service/app/core/chat_graph/langsmith_trace.py`
- runtime hooks:
  - `run_start` / `node` / `run_end` / `run_error`
  - metadata: `trace_id`, `request_id`, `session_id`, `route`, `reason_code`, `state_version`
- control flags:
  - `QS_CHAT_LANGSMITH_ENABLED=1`
  - `QS_CHAT_LANGSMITH_KILL_SWITCH=1` (즉시 차단)
  - `QS_CHAT_LANGSMITH_SAMPLE_RATE=0.1`
  - `QS_CHAT_LANGSMITH_SAMPLE_OVERRIDES_JSON='{\"tenants\":{\"tenant-a\":1.0},\"channels\":{\"web\":0.2}}'`
  - `QS_CHAT_LANGSMITH_REDACTION_MODE=masked_raw|hash_summary` (기본 `hash_summary`)
- export target:
  - `QS_CHAT_LANGSMITH_ENDPOINT` (default `https://api.smith.langchain.com/runs`)
  - `QS_CHAT_LANGSMITH_API_KEY`
  - `QS_CHAT_LANGSMITH_PROJECT`
- audit summary:
```bash
python scripts/eval/chat_langsmith_trace_summary.py --limit 200
```

## Chat OpenFeature-style routing (B-0712)
- router module: `services/query-service/app/core/chat_graph/feature_router.py`
- flags:
  - `QS_CHAT_FORCE_LEGACY`
  - `QS_CHAT_LANGGRAPH_ENABLED`
  - `QS_CHAT_OPENFEATURE_FLAGS_JSON` (`chat.engine.mode`, `chat.force_legacy`, `chat.langgraph.enabled`)

## Chat shadow comparator (B-0713)
- comparator module: `services/query-service/app/core/chat_graph/shadow_comparator.py`
- summary script:
```bash
python scripts/eval/chat_shadow_summary.py --limit 200
```

## Chat canary gate + auto rollback (B-0714)
- controller module: `services/query-service/app/core/chat_graph/canary_controller.py`
- apply script:
```bash
python scripts/eval/chat_canary_gate.py --limit 200 --apply
```
- rollout stage guideline:
  - `shadow(0%) -> canary(5%) -> 10% -> 25% -> 50% -> 100%`
  - 단계별 dwell: 최소 30분, `BLOCKER` 비율 임계치 초과 시 즉시 force-legacy

## Chat reason-code taxonomy governance gate (B-0715)
- taxonomy module: `services/query-service/app/core/chat_graph/reason_taxonomy.py`
- runtime metrics:
  - `chat_reason_code_total{source,reason_code}`
  - `chat_reason_code_invalid_total{source}`
  - `chat_reason_code_unknown_total{source}`
  - `chat_reason_code_invalid_ratio{source}`
  - `chat_reason_code_unknown_ratio{source}`
- eval script:
```bash
python scripts/eval/chat_reason_taxonomy_eval.py \
  --cases-json services/query-service/tests/fixtures/chat_reason_taxonomy_cases_v1.json \
  --responses-json services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json \
  --gate
```
- CI 옵션:
  - `RUN_CHAT_REASON_TAXONOMY_EVAL=1 ./scripts/test.sh`

## Chat domain node migration (B-0721, in-progress)
- domain module: `services/query-service/app/core/chat_graph/domain_nodes.py`
- 적용 범위:
  - Book query 정규화(`ISBN/권차/시리즈`)
  - selection memory cache (`chat:graph:selection:{session_id}`)
  - 참조 해소 (`2번째`, `그거`, `아까 추천`)
  - policy topic cache (`RefundPolicy`, `ShippingPolicy`, `OrderCancelPolicy`, `EbookRefundPolicy`)
- 정책 캐시 제어:
  - `QS_CHAT_POLICY_TOPIC_VERSION` (버전 변경 시 cache key 자동 분리)
  - `QS_CHAT_POLICY_CACHE_TTL_SEC`
  - `QS_CHAT_SELECTION_TTL_SEC`

## Compose + claim verifier node (B-0722, in-progress)
- compose node:
  - route별 UI hint 생성(`options/cards/forms/buttons`)
  - 공개 응답 계약(`chat-response.schema.json`)을 유지하기 위해 현재는 `tool_result.data.ui_hints`에 내부 저장
- claim verifier node:
  - 완료 claim 문구(조회/실행/취소/환불 완료) 검증
  - 근거 부족 또는 confirmation 미완료 상태에서 `OUTPUT_GUARD_FORBIDDEN_CLAIM`으로 자동 차단/복구
- metrics:
  - `chat_graph_ui_hint_render_total{route,type}`
  - `chat_graph_claim_verifier_total{result,reason}`

## Eval harness migration (B-0723, in-progress)
- parity eval:
```bash
python scripts/eval/chat_graph_parity_eval.py \
  --shadow-limit 200 \
  --replay-dir var/chat_graph/replay \
  --gate
```
- unified matrix:
```bash
python scripts/eval/chat_eval_matrix.py \
  --cases-json services/query-service/tests/fixtures/chat_contract_compat_v1.json \
  --responses-json services/query-service/tests/fixtures/chat_reason_taxonomy_responses_v1.json \
  --contracts-root . \
  --replay-dir var/chat_graph/replay \
  --gate
```
- CI 옵션:
  - `RUN_CHAT_ALL_EVALS=1 ./scripts/test.sh`
  - baseline 파일:
    - `data/eval/reports/chat_graph_parity_eval_baseline.json`
    - `data/eval/reports/chat_eval_matrix_baseline.json`

## Performance budget + cutover gate (B-0724, in-progress)
- perf budget module: `services/query-service/app/core/chat_graph/perf_budget.py`
  - `chat_graph_perf_sample_total`
  - `chat_graph_runtime_latency_ms`
- 주요 예산 env:
  - `QS_CHAT_BUDGET_NON_LLM_P95_MS` (default `600`)
  - `QS_CHAT_BUDGET_LLM_P95_MS` (default `4000`)
  - `QS_CHAT_BUDGET_MAX_AVG_TOOL_CALLS` (default `1.5`)
  - `QS_CHAT_BUDGET_MAX_FALLBACK_RATIO` (default `0.15`)
- cutover gate:
```bash
python scripts/eval/chat_cutover_gate.py \
  --current-stage 25 \
  --dwell-minutes 45
```
- CI 옵션:
  - `RUN_CHAT_CUTOVER_GATE=1 ./scripts/test.sh`

## Legacy decommission enforcement (B-0724 follow-up)
- routing audit 집계:
  - session별: `chat:graph:routing-audit:{session_id}`
  - global window: `chat:graph:routing-audit:global`
- feature router summary API:
  - `load_global_routing_audit(limit)`
  - `build_legacy_mode_summary(limit)`
- decommission 제어 플래그:
  - `QS_CHAT_LEGACY_DECOMMISSION_ENABLED=1` (legacy 경로 기본 차단)
  - `QS_CHAT_LEGACY_EMERGENCY_RECOVERY=1` (긴급 복구 시 legacy 임시 허용)
  - OpenFeature 키: `chat.legacy.decommission.enabled`, `chat.legacy.emergency_recovery`
- gate script:
```bash
python scripts/eval/chat_legacy_decommission_check.py \
  --limit 500 \
  --min-window 20 \
  --max-legacy-count 0 \
  --max-legacy-ratio 0.0 \
  --allow-legacy-reasons legacy_emergency_recovery,auto_rollback_override \
  --gate
```
- CI 옵션:
  - `RUN_CHAT_LEGACY_DECOMMISSION_CHECK=1 ./scripts/test.sh`

## Production launch readiness gate (B-0391-lite)
- 통합 gate 스크립트:
```bash
python scripts/eval/chat_production_launch_gate.py \
  --replay-dir var/chat_graph/replay \
  --completion-source auto \
  --model-version "$QS_LLM_MODEL" \
  --prompt-version "$QS_CHAT_PROMPT_VERSION" \
  --policy-version "$QS_CHAT_POLICY_VERSION" \
  --baseline-report data/eval/reports/chat_production_launch_gate_baseline.json \
  --parity-limit 200 \
  --perf-limit 500 \
  --reason-limit 500 \
  --legacy-limit 500 \
  --run-limit 300 \
  --min-reason-window 20 \
  --min-legacy-window 20 \
  --min-run-window 20 \
  --min-commerce-samples 10 \
  --max-mismatch-ratio 0.10 \
  --max-blocker-ratio 0.02 \
  --max-reason-invalid-ratio 0.0 \
  --max-reason-unknown-ratio 0.05 \
  --max-legacy-ratio 0.0 \
  --max-legacy-count 0 \
  --min-commerce-completion-rate 0.90 \
  --max-insufficient-evidence-ratio 0.30 \
  --triage-out var/chat_graph/triage/chat_launch_failure_cases.jsonl \
  --gate
```
- 집계 소스:
  - parity/canary: `shadow_comparator`, `canary_controller`
  - perf budget: `perf_budget`
  - reason taxonomy: `reason_taxonomy`
  - legacy decommission: `feature_router` global routing audit
  - completion: `launch_metrics`(우선) 또는 `var/chat_graph/replay/runs/*.json`(fallback)
- triage queue:
  - gate 실패 시 샘플 케이스를 JSONL로 적재
  - 기본 경로: `var/chat_graph/triage/chat_launch_failure_cases.jsonl`
- 런타임 launch metric 누적:
  - 모듈: `services/query-service/app/core/chat_graph/launch_metrics.py`
  - 메트릭: `chat_completion_total`, `chat_completion_rate{intent}`, `chat_insufficient_evidence_total`, `chat_insufficient_evidence_rate{domain}`
- fallback 템플릿 표준화:
  - 구현 위치: `services/query-service/app/core/chat_graph/runtime.py::_fallback_template`
  - `insufficient_evidence` 경로는 reason_code별 한국어 안내 + 기본 `next_action`/`retry_after_ms`를 강제
- CI 옵션:
  - `RUN_CHAT_PROD_LAUNCH_GATE=1 ./scripts/test.sh`
  - baseline 파일이 있을 때만 자동 비교 (`CHAT_PROD_LAUNCH_BASELINE_PATH`)

## Release train decision gate (I-0360-lite)
- launch gate 리포트 + cutover 정책을 결합해 `promote/hold/rollback` 결정:
```bash
python scripts/eval/chat_release_train_gate.py \
  --reports-dir data/eval/reports \
  --report-prefix chat_production_launch_gate \
  --current-stage 25 \
  --dwell-minutes 45
```
- 자동 rollback 적용(옵션):
```bash
python scripts/eval/chat_release_train_gate.py \
  --current-stage 25 \
  --dwell-minutes 45 \
  --apply-rollback
```
- CI 옵션:
  - `RUN_CHAT_RELEASE_TRAIN_GATE=1 ./scripts/test.sh`

## LiveOps cycle orchestrator (I-0360, Bundle 2)
- launch gate + release train 결정을 한 번에 실행:
```bash
python scripts/eval/chat_liveops_cycle.py \
  --out data/eval/reports \
  --replay-dir var/chat_graph/replay \
  --completion-source auto \
  --current-stage 25 \
  --dwell-minutes 45
```
- 옵션:
  - `--baseline-report ...` : launch gate baseline 회귀 비교 포함
  - `--apply-rollback` : rollback 결정 시 force-legacy override 즉시 적용
  - `--require-promote` : 결과가 promote가 아니면 실패 처리
- CI 옵션:
  - `RUN_CHAT_LIVEOPS_CYCLE=1 ./scripts/test.sh`

## LiveOps summary gate (I-0360, Bundle 3)
- 최근 liveops cycle 리포트 집계:
```bash
python scripts/eval/chat_liveops_summary.py \
  --reports-dir data/eval/reports \
  --limit 20 \
  --min-window 3 \
  --min-pass-ratio 0.8 \
  --deny-actions rollback \
  --gate
```
- CI 옵션:
  - `RUN_CHAT_LIVEOPS_SUMMARY_GATE=1 ./scripts/test.sh`

## LiveOps incident MTTA/MTTR gate (I-0360, Bundle 4)
- 최근 cycle 리포트 기반 incident 지표 집계:
```bash
python scripts/eval/chat_liveops_incident_summary.py \
  --reports-dir data/eval/reports \
  --limit 20 \
  --min-window 3 \
  --max-mtta-sec 600 \
  --max-mttr-sec 7200 \
  --max-open-incidents 0 \
  --gate
```
- CI 옵션:
  - `RUN_CHAT_LIVEOPS_INCIDENT_GATE=1 ./scripts/test.sh`

## On-call action plan generator (I-0360, Bundle 5)
- triage queue를 기반으로 우선순위 조치안 자동 생성:
```bash
python scripts/eval/chat_oncall_action_plan.py \
  --triage-file var/chat_graph/triage/chat_launch_failure_cases.jsonl \
  --out data/eval/reports \
  --top-n 5
```
- CI 옵션:
  - `RUN_CHAT_ONCALL_ACTION_PLAN=1 ./scripts/test.sh`

## Capacity/Cost guard gate (I-0360, Bundle 6)
- launch gate 성능 + LLM audit 로그를 결합해 load shedding 단계를 결정:
```bash
python scripts/eval/chat_capacity_cost_guard.py \
  --reports-dir data/eval/reports \
  --report-prefix chat_production_launch_gate \
  --llm-audit-log var/llm_gateway/audit.log \
  --audit-window-minutes 60 \
  --max-mode DEGRADE_LEVEL_1 \
  --gate
```
- 출력 mode:
  - `NORMAL`, `DEGRADE_LEVEL_1`, `DEGRADE_LEVEL_2`, `FAIL_CLOSED`
- CI 옵션:
  - `RUN_CHAT_CAPACITY_COST_GUARD=1 ./scripts/test.sh`

## Immutable bundle guard (I-0360, Bundle 7)
- liveops cycle 리포트에서 release_signature 변경 드리프트를 감시:
```bash
python scripts/eval/chat_immutable_bundle_guard.py \
  --reports-dir data/eval/reports \
  --prefix chat_liveops_cycle \
  --limit 20 \
  --min-window 3 \
  --max-unique-signatures 2 \
  --max-signature-changes 2 \
  --allowed-change-actions promote,rollback \
  --require-signature \
  --gate
```
- 검증 항목:
  - signature 누락 여부
  - 허용되지 않은 action에서의 signature 변경 여부
  - window 내 signature 변화량 상한
- CI 옵션:
  - `RUN_CHAT_IMMUTABLE_BUNDLE_GUARD=1 ./scripts/test.sh`

## DR drill report (I-0360, Bundle 8)
- liveops cycle에서 rollback drill 복구 무결성을 월간/주간 리포트로 저장:
```bash
python scripts/eval/chat_dr_drill_report.py \
  --reports-dir data/eval/reports \
  --prefix chat_liveops_cycle \
  --limit 40 \
  --out data/eval/reports \
  --min-window 1 \
  --min-recovery-ratio 1.0 \
  --max-open-drill-total 0 \
  --max-avg-mttr-sec 7200 \
  --gate
```
- 필요 시 실제 drill 강제:
  - `--require-drill`
- CI 옵션:
  - `RUN_CHAT_DR_DRILL_REPORT=1 ./scripts/test.sh`

## Production readiness score (I-0361, Bundle 1)
- launch/liveops/incident/drill/capacity 신호를 종합해 readiness 점수 계산:
```bash
python scripts/eval/chat_readiness_score.py \
  --reports-dir data/eval/reports \
  --launch-prefix chat_production_launch_gate \
  --cycle-prefix chat_liveops_cycle \
  --cycle-limit 20 \
  --llm-audit-log var/llm_gateway/audit.log \
  --min-score 80 \
  --capacity-max-mode DEGRADE_LEVEL_1 \
  --out data/eval/reports \
  --gate
```
- 산출물:
  - score/tier(`READY|WATCH|HOLD`)
  - recommended_action(`promote|hold`)
  - blocker/warning 목록
- CI 옵션:
  - `RUN_CHAT_READINESS_SCORE=1 ./scripts/test.sh`

## Readiness trend gate (I-0361, Bundle 4)
- readiness 점수 리포트의 주/월 평균 추세와 다음 목표 점수를 자동 계산:
```bash
python scripts/eval/chat_readiness_trend.py \
  --reports-dir data/eval/reports \
  --prefix chat_readiness_score \
  --limit 200 \
  --out data/eval/reports \
  --min-reports 1 \
  --min-week-avg 80 \
  --min-month-avg 80 \
  --gate
```
- 산출물:
  - current/previous week, month 평균 및 delta
  - target_next_week / target_next_month
- CI 옵션:
  - `RUN_CHAT_READINESS_TREND=1 ./scripts/test.sh`

## Gameday drillpack template (I-0361, Bundle 2)
- triage reason 분포를 반영해 장애 훈련 체크리스트 자동 생성:
```bash
python scripts/eval/chat_gameday_drillpack.py \
  --triage-file var/chat_graph/triage/chat_launch_failure_cases.jsonl \
  --top-reasons 5 \
  --out data/eval/reports \
  --gate
```
- 필요 시 triage 데이터 강제:
  - `--require-triage`
- CI 옵션:
  - `RUN_CHAT_GAMEDAY_DRILLPACK=1 ./scripts/test.sh`

## Incident feedback binding (I-0361, Bundle 3)
- 실제 incident와 triage reason을 drill taxonomy로 자동 매핑:
```bash
python scripts/eval/chat_incident_feedback_binding.py \
  --reports-dir data/eval/reports \
  --cycle-prefix chat_liveops_cycle \
  --cycle-limit 40 \
  --triage-file var/chat_graph/triage/chat_launch_failure_cases.jsonl \
  --top-n 5 \
  --out data/eval/reports \
  --min-bound-categories 1 \
  --gate
```
- 산출물:
  - bound category 집계(incident/triage split)
  - 다음 drillpack 반영 권고안
- CI 옵션:
  - `RUN_CHAT_INCIDENT_FEEDBACK_BINDING=1 ./scripts/test.sh`

## Gameday readiness packet (I-0361, Bundle 5)
- readiness/trend/drill/feedback 산출물을 하나의 배포 판단 패킷으로 결합:
```bash
python scripts/eval/chat_gameday_readiness_packet.py \
  --reports-dir data/eval/reports \
  --min-readiness-score 80 \
  --min-week-avg 80 \
  --out data/eval/reports \
  --gate
```
- 옵션:
  - `--require-all` (필수 리포트 누락 시 실패)
- CI 옵션:
  - `RUN_CHAT_GAMEDAY_PACKET=1 ./scripts/test.sh`

## Data retention guard (I-0362, Bundle 1)
- retention lifecycle 이벤트를 기준으로 TTL 만료/삭제/예외 승인 준수 여부를 게이트로 평가:
```bash
python scripts/eval/chat_data_retention_guard.py \
  --events-jsonl var/chat_governance/retention_events.jsonl \
  --window-hours 72 \
  --out data/eval/reports \
  --min-window 1 \
  --max-overdue-total 0 \
  --max-overdue-ratio 0.0 \
  --min-purge-coverage-ratio 1.0 \
  --max-unapproved-exception-total 0 \
  --max-stale-minutes 180 \
  --min-trace-coverage-ratio 1.0 \
  --max-missing-trace-total 0 \
  --gate
```
- 산출물:
  - 데이터 클래스별 만료/삭제/미처리(overdue) 집계
  - 승인 없는 보관 예외(unapproved exception) 탐지
  - trace/request 연결 커버리지 및 stale window
- CI 옵션:
  - `RUN_CHAT_DATA_RETENTION_GUARD=1 ./scripts/test.sh`

## Egress guardrails gate (I-0362, Bundle 2)
- outbound 전송 이벤트를 기준으로 allowlist 위반/민감필드 비마스킹/trace 누락을 게이트로 차단:
```bash
python scripts/eval/chat_egress_guardrails_gate.py \
  --events-jsonl var/chat_governance/egress_events.jsonl \
  --allow-destinations llm_provider,langsmith,support_api \
  --window-hours 24 \
  --out data/eval/reports \
  --min-window 1 \
  --max-violation-total 0 \
  --max-unmasked-sensitive-total 0 \
  --max-unknown-destination-total 0 \
  --max-error-ratio 0.05 \
  --max-missing-trace-total 0 \
  --min-alert-coverage-ratio 1.0 \
  --max-stale-minutes 180 \
  --gate
```
- 산출물:
  - destination별 total/violation/blocked 분포
  - unmasked sensitive egress / unknown destination 탐지
  - violation 대비 alert coverage 비율
- CI 옵션:
  - `RUN_CHAT_EGRESS_GUARDRAILS_GATE=1 ./scripts/test.sh`

## Data governance evidence packet (I-0362, Bundle 3)
- retention/egress 게이트 결과를 묶어 감사 대응용 증적 리포트와 최종 상태를 생성:
```bash
python scripts/eval/chat_data_governance_evidence.py \
  --reports-dir data/eval/reports \
  --retention-prefix chat_data_retention_guard \
  --egress-prefix chat_egress_guardrails_gate \
  --min-trace-coverage-ratio 1.0 \
  --min-lifecycle-score 80 \
  --require-reports \
  --require-events \
  --out data/eval/reports \
  --gate
```
- 산출물:
  - 최종 상태(`READY|WATCH|HOLD`) 및 권장 액션(`promote|hold`)
  - lifecycle score + trace coverage
  - retention/egress 근거 리포트 경로 및 blocker/warning 목록
- CI 옵션:
  - `RUN_CHAT_DATA_GOV_EVIDENCE_GATE=1 ./scripts/test.sh`

## Load profile model gate (I-0363, Bundle 1)
- 트래픽 이벤트에서 시간대/의도/툴사용/지연/오류를 시나리오별(`NORMAL|PROMOTION|INCIDENT`) 프로파일로 집계:
```bash
python scripts/eval/chat_load_profile_model.py \
  --traffic-jsonl var/chat_governance/load_events.jsonl \
  --window-hours 168 \
  --out data/eval/reports \
  --min-window 1 \
  --max-normal-error-ratio 0.05 \
  --max-normal-p95-latency-ms 3000 \
  --max-normal-p95-queue-depth 50 \
  --gate
```
- 산출물:
  - 시나리오별 request/error/tool usage/latency(queue p95) 프로파일
  - 시간대(hour UTC)별 부하 분포와 상위 intent 분포
  - 정상 구간(`NORMAL`) 기준 임계치 위반 여부
- CI 옵션:
  - `RUN_CHAT_LOAD_PROFILE_MODEL=1 ./scripts/test.sh`

## Capacity forecast gate (I-0363, Bundle 2)
- load profile 리포트를 입력으로 주/월 수요/토큰/툴콜과 리소스(CPU/GPU/메모리)·비용을 예측:
```bash
python scripts/eval/chat_capacity_forecast.py \
  --reports-dir data/eval/reports \
  --load-prefix chat_load_profile_model \
  --baseline-window-hours 168 \
  --weekly-growth-factor 1.08 \
  --monthly-growth-factor 1.35 \
  --promo-surge-factor 1.6 \
  --cpu-rps-per-core 3.0 \
  --gpu-tokens-per-sec 800 \
  --cost-per-1k-tokens 0.002 \
  --max-peak-rps 50 \
  --max-monthly-cost-usd 15000 \
  --max-cpu-cores 64 \
  --max-gpu-required 8 \
  --gate
```
- 산출물:
  - week/month requests, tokens, tool_calls forecast
  - peak_rps 및 필요 CPU/GPU/메모리 추정
  - 월 비용 추정치와 임계치 위반 여부
- CI 옵션:
  - `RUN_CHAT_CAPACITY_FORECAST=1 ./scripts/test.sh`

## Autoscaling calibration gate (I-0363, Bundle 3)
- forecast 결과와 autoscaling 실측 이벤트를 비교해 과소/과잉 할당 비율 및 보정 계수를 계산:
```bash
python scripts/eval/chat_autoscaling_calibration.py \
  --events-jsonl var/chat_governance/autoscaling_events.jsonl \
  --reports-dir data/eval/reports \
  --capacity-forecast-prefix chat_capacity_forecast \
  --window-hours 168 \
  --under-tolerance-ratio 0.05 \
  --over-tolerance-ratio 0.10 \
  --base-prescale-factor 1.20 \
  --calibration-step 0.05 \
  --max-under-ratio 0.10 \
  --max-over-ratio 0.35 \
  --max-prediction-mape 0.40 \
  --max-canary-failure-total 0 \
  --require-release-canary \
  --gate
```
- 산출물:
  - under/over provisioning ratio, prediction MAPE
  - release canary 실패 집계
  - target prescale factor 및 recommended peak rps
- CI 옵션:
  - `RUN_CHAT_AUTOSCALING_CALIBRATION=1 ./scripts/test.sh`

## Session gateway durability gate (I-0364, Bundle 1)
- 세션 연결/재연결/resume/heartbeat 이벤트를 분석해 SSE 세션 복구 안정성을 게이트로 검증:
```bash
python scripts/eval/chat_session_gateway_durability.py \
  --events-jsonl var/chat_governance/session_gateway_events.jsonl \
  --window-hours 24 \
  --heartbeat-lag-threshold-ms 30000 \
  --min-reconnect-success-rate 0.95 \
  --min-resume-success-rate 0.98 \
  --max-heartbeat-miss-ratio 0.05 \
  --max-affinity-miss-ratio 0.02 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - reconnect/resume 성공률
  - heartbeat miss ratio 및 affinity miss ratio
  - active connection/세션 규모와 stale window
- CI 옵션:
  - `RUN_CHAT_SESSION_DURABILITY_GATE=1 ./scripts/test.sh`

## Event delivery guarantee gate (I-0364, Bundle 2)
- turn/event 전달 로그를 기반으로 ordered delivery, duplicate, ACK 누락, redelivery TTL 드롭을 검증:
```bash
python scripts/eval/chat_event_delivery_guarantee.py \
  --events-jsonl var/chat_governance/event_delivery_events.jsonl \
  --window-hours 24 \
  --min-delivery-success-ratio 0.99 \
  --max-order-violation-total 0 \
  --max-duplicate-ratio 0.01 \
  --max-ack-missing-ratio 0.02 \
  --max-sync-gap 5 \
  --max-ttl-drop-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - delivery success ratio, ordered violation total
  - duplicate/ack-missing ratio, redelivery/TTL drop 집계
  - reconnect 이후 sync gap 최대치
- CI 옵션:
  - `RUN_CHAT_EVENT_DELIVERY_GUARANTEE=1 ./scripts/test.sh`

## Backpressure admission guard (I-0364, Bundle 3)
- backpressure 이벤트에서 우선순위별 drop/큐 지표/핵심 인텐트 보호율/사용자 안내 누락을 검증:
```bash
python scripts/eval/chat_backpressure_admission_guard.py \
  --events-jsonl var/chat_governance/backpressure_events.jsonl \
  --window-hours 24 \
  --max-drop-ratio 0.20 \
  --max-critical-drop-total 0 \
  --min-core-protected-ratio 0.98 \
  --max-p95-queue-depth 80 \
  --max-p95-queue-latency-ms 3000 \
  --max-guidance-missing-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - priority별 admitted/dropped 분포
  - core intent protected ratio
  - queue p95(depth/latency) 및 circuit-open 안내 누락
- CI 옵션:
  - `RUN_CHAT_BACKPRESSURE_ADMISSION_GUARD=1 ./scripts/test.sh`

## Session resilience drill report gate (I-0364, Bundle 4)
- connection storm/partial region fail/broker delay 게임데이 결과를 집계해 RTO/손실률/커버리지를 검증:
```bash
python scripts/eval/chat_session_resilience_drill_report.py \
  --events-jsonl var/chat_governance/session_resilience_drills.jsonl \
  --window-days 30 \
  --required-scenarios CONNECTION_STORM,PARTIAL_REGION_FAIL,BROKER_DELAY \
  --max-open-drill-total 0 \
  --max-avg-rto-sec 900 \
  --max-message-loss-ratio 0.001 \
  --max-stale-days 35 \
  --require-scenarios \
  --gate
```
- 산출물:
  - scenario별 run/success/failure/open drill 집계
  - avg/max RTO 및 message loss ratio
  - 필수 시나리오 누락 여부
- CI 옵션:
  - `RUN_CHAT_SESSION_RESILIENCE_DRILL_REPORT=1 ./scripts/test.sh`

## Unit economics SLO gate (I-0365, Bundle 1)
- 세션 비용 이벤트에서 cost-to-resolve와 unresolved burn을 계산해 FinOps SLO를 게이트로 검증:
```bash
python scripts/eval/chat_unit_economics_slo.py \
  --events-jsonl var/chat_finops/session_cost_events.jsonl \
  --window-days 7 \
  --min-resolution-rate 0.80 \
  --max-cost-per-resolved-session 2.0 \
  --max-unresolved-cost-burn-total 200 \
  --max-tool-cost-mix-ratio 0.80 \
  --max-stale-days 8 \
  --gate
```
- 산출물:
  - cost_per_resolved_session, unresolved_cost_burn_total
  - tool/token cost mix ratio
  - resolution rate 기반 품질 제약 여부
- CI 옵션:
  - `RUN_CHAT_UNIT_ECONOMICS_SLO=1 ./scripts/test.sh`

## Cost optimizer policy gate (I-0365, Bundle 2)
- 예산 압력과 품질 제약을 함께 고려해 intent별 라우팅 정책(`NORMAL/SOFT_CLAMP/HARD_CLAMP`)을 계산:
```bash
python scripts/eval/chat_cost_optimizer_policy.py \
  --events-jsonl var/chat_finops/session_cost_events.jsonl \
  --window-days 7 \
  --soft-budget-utilization 0.75 \
  --hard-budget-utilization 0.90 \
  --min-resolution-rate 0.80 \
  --max-cost-per-resolved-session 2.5 \
  --high-risk-intents CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE \
  --gate
```
- 산출물:
  - clamp mode 결정(`NORMAL/SOFT_CLAMP/HARD_CLAMP`)
  - intent별 route policy(`TRUSTED/BALANCED/LIGHT`)와 적용 사유
  - budget 압력 기반 예상 절감 비용(`estimated_savings_total_usd`)
- CI 옵션:
  - `RUN_CHAT_COST_OPTIMIZER_POLICY=1 ./scripts/test.sh`

## Budget release guard gate (I-0365, Bundle 3)
- forecast/unit-economics/optimizer 리포트를 결합해 릴리스 예산 안전성(`PROMOTE/HOLD/BLOCK`)을 계산:
```bash
python scripts/eval/chat_budget_release_guard.py \
  --reports-dir data/eval/reports \
  --forecast-prefix chat_capacity_forecast \
  --unit-econ-prefix chat_unit_economics_slo \
  --optimizer-prefix chat_cost_optimizer_policy \
  --monthly-budget-limit-usd 15000 \
  --max-budget-utilization 0.90 \
  --max-unresolved-cost-burn-total 200 \
  --min-resolution-rate 0.80 \
  --gate
```
- 산출물:
  - post-optimizer budget utilization 기반 release_state(`PROMOTE/HOLD/BLOCK`)
  - quality/cost/budget 위반 원인 목록
  - optimizer mode와 clamp 필요 여부 점검 결과
- CI 옵션:
  - `RUN_CHAT_BUDGET_RELEASE_GUARD=1 ./scripts/test.sh`

## FinOps tradeoff report gate (I-0365, Bundle 4)
- unit economics/예산가드/감사로그를 합쳐 cost-quality 트레이드오프를 주간 리포트로 평가:
```bash
python scripts/eval/chat_finops_tradeoff_report.py \
  --reports-dir data/eval/reports \
  --unit-prefix chat_unit_economics_slo \
  --budget-prefix chat_budget_release_guard \
  --llm-audit-log var/llm_gateway/audit.log \
  --report-limit 30 \
  --min-tradeoff-index 0.20 \
  --max-avg-cost-per-resolved-session 2.5 \
  --max-avg-unresolved-cost-burn-total 200 \
  --gate
```
- 산출물:
  - avg cost-per-resolved / resolution / unresolved burn / budget utilization
  - tradeoff index와 cost-down 대비 quality 저하 여부
  - reason_code별 비용 급등(top reasons) 분해
- CI 옵션:
  - `RUN_CHAT_FINOPS_TRADEOFF_REPORT=1 ./scripts/test.sh`

## Config distribution rollout gate (I-0366, Bundle 1)
- 실시간 정책 번들 배포 이벤트를 집계해 서명/단계 롤아웃/드리프트 상태를 검증:
```bash
python scripts/eval/chat_config_distribution_rollout.py \
  --events-jsonl var/chat_control/config_rollout_events.jsonl \
  --window-hours 24 \
  --required-stages 1,10,50,100 \
  --min-success-ratio 0.95 \
  --max-drift-ratio 0.02 \
  --max-signature-invalid-total 0 \
  --max-stage-regression-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - rollout success ratio, signature invalid total
  - config drift ratio 및 서비스별 drift 집계
  - bundle별 stage progress와 missing required stage
- CI 옵션:
  - `RUN_CHAT_CONFIG_DISTRIBUTION_ROLLOUT=1 ./scripts/test.sh`

## Config safety guard gate (I-0366, Bundle 2)
- 배포 중 이상 감지 시 auto-stop/rollback/kill-switch 대응이 충분했는지 검증:
```bash
python scripts/eval/chat_config_safety_guard.py \
  --events-jsonl var/chat_control/config_guard_events.jsonl \
  --window-hours 24 \
  --forbidden-killswitch-scopes GLOBAL_ALL_SERVICES \
  --max-unhandled-anomaly-total 0 \
  --min-mitigation-ratio 0.95 \
  --max-detection-lag-p95-sec 120 \
  --max-forbidden-killswitch-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - anomaly/handled/unhandled 집계와 mitigation ratio
  - auto-stop/auto-rollback/killswitch 집계
  - detection lag p95 및 forbidden scope kill-switch 위반
- CI 옵션:
  - `RUN_CHAT_CONFIG_SAFETY_GUARD=1 ./scripts/test.sh`

## Config audit reproducibility gate (I-0366, Bundle 3)
- 누가/언제/무엇을 배포했는지 감사 증적과 snapshot replay 가능성을 검증:
```bash
python scripts/eval/chat_config_audit_reproducibility.py \
  --events-jsonl var/chat_control/config_audit_events.jsonl \
  --snapshots-dir var/chat_control/snapshots \
  --window-hours 24 \
  --max-missing-actor-total 0 \
  --max-missing-trace-total 0 \
  --max-immutable-violation-total 0 \
  --min-snapshot-replay-ratio 0.95 \
  --min-diff-coverage-ratio 0.95 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - actor/request/trace 누락 건수
  - immutable 위반 건수
  - snapshot replay ratio / diff coverage ratio
- CI 옵션:
  - `RUN_CHAT_CONFIG_AUDIT_REPRO_GUARD=1 ./scripts/test.sh`

## Config ops runbook integration gate (I-0366, Bundle 4)
- 실패 유형별 플레이북 연결과 온콜 알림 payload(버전/영향서비스/권장조치) 완전성을 검증:
```bash
python scripts/eval/chat_config_ops_runbook_integration.py \
  --events-jsonl var/chat_control/config_ops_events.jsonl \
  --window-hours 24 \
  --min-payload-complete-ratio 0.95 \
  --max-missing-runbook-total 0 \
  --max-missing-recommended-action-total 0 \
  --max-missing-bundle-version-total 0 \
  --max-missing-impacted-services-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - payload complete ratio
  - runbook/recommended_action/bundle_version/impacted_services 누락 건수
  - incident type별 분포
- CI 옵션:
  - `RUN_CHAT_CONFIG_OPS_RUNBOOK_INTEGRATION=1 ./scripts/test.sh`

## Workflow state model gate (B-0367, Bundle 1)
- 멀티스텝 커머스 워크플로우 상태 모델 필드 완전성과 템플릿 지원 범위를 검증:
```bash
python scripts/eval/chat_workflow_state_model.py \
  --events-jsonl var/chat_workflow/workflow_events.jsonl \
  --window-hours 24 \
  --max-missing-state-fields-total 0 \
  --max-unsupported-type-total 0 \
  --min-checkpoint-ratio 0.80 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - workflow/state record 집계
  - missing state fields / unsupported workflow type 건수
  - checkpoint ratio 및 템플릿 누락 여부
- CI 옵션:
  - `RUN_CHAT_WORKFLOW_STATE_MODEL=1 ./scripts/test.sh`

## Workflow plan-execute gate (B-0367, Bundle 2)
- 워크플로우 단계 순서(의도확인→입력수집→검증→실행)와 재진입 성공률을 검증:
```bash
python scripts/eval/chat_workflow_plan_execute.py \
  --events-jsonl var/chat_workflow/workflow_events.jsonl \
  --window-hours 24 \
  --min-sequence-valid-ratio 0.95 \
  --min-validation-before-execute-ratio 0.99 \
  --max-step-error-total 0 \
  --min-reentry-success-ratio 0.80 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - sequence valid ratio
  - validation-before-execute ratio
  - step error total / reentry success ratio
- CI 옵션:
  - `RUN_CHAT_WORKFLOW_PLAN_EXECUTE=1 ./scripts/test.sh`

## Workflow confirmation checkpoint gate (B-0367, Bundle 3)
- 민감 액션 실행 전 최종 확인 누락과 timeout 자동취소 정책 준수 여부를 검증:
```bash
python scripts/eval/chat_workflow_confirmation_checkpoint.py \
  --events-jsonl var/chat_workflow/workflow_events.jsonl \
  --window-hours 24 \
  --max-execute-without-confirmation-total 0 \
  --min-timeout-auto-cancel-ratio 1.0 \
  --max-confirmation-latency-p95-sec 300 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - sensitive execute 대비 무확인 실행 건수
  - confirmation timeout 대비 auto-cancel 비율
  - confirmation latency p95
- CI 옵션:
  - `RUN_CHAT_WORKFLOW_CONFIRM_CHECKPOINT=1 ./scripts/test.sh`

## Workflow recovery audit gate (B-0367, Bundle 4)
- 세션 중단 후 복원 성공률과 단계별 감사로그 완전성(멱등성 포함)을 검증:
```bash
python scripts/eval/chat_workflow_recovery_audit.py \
  --events-jsonl var/chat_workflow/workflow_events.jsonl \
  --window-hours 24 \
  --min-recovery-success-ratio 0.95 \
  --max-recovery-latency-p95-sec 600 \
  --max-audit-missing-fields-total 0 \
  --max-write-without-idempotency-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - interrupted/recovered 집계 및 recovery success ratio
  - recovery latency p95
  - audit missing fields / write without idempotency 건수
- CI 옵션:
  - `RUN_CHAT_WORKFLOW_RECOVERY_AUDIT=1 ./scripts/test.sh`

## Source trust registry gate (B-0368, Bundle 1)
- 출처 신뢰도 정책 레지스트리의 커버리지/정합성/신선도를 검증:
```bash
python scripts/eval/chat_source_trust_registry.py \
  --policy-json var/chat_trust/source_trust_policy.json \
  --max-policy-age-days 7 \
  --min-policy-total 1 \
  --min-coverage-ratio 1.0 \
  --max-invalid-weight-total 0 \
  --max-invalid-ttl-total 0 \
  --max-missing-version-total 0 \
  --max-stale-ratio 0.10 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - source type coverage ratio 및 missing source types
  - trust weight/TTL/version 유효성 위반 건수
  - 최신 정책 시각 기반 stale ratio/stale minutes
- CI 옵션:
  - `RUN_CHAT_SOURCE_TRUST_REGISTRY=1 ./scripts/test.sh`

## Trust rerank integration gate (B-0368, Bundle 2)
- trust-aware 점수(신뢰도 boost + stale penalty)가 top-k 노출 품질을 개선하는지 검증:
```bash
python scripts/eval/chat_trust_rerank_integration.py \
  --events-jsonl var/chat_trust/retrieval_events.jsonl \
  --window-hours 24 \
  --top-k 3 \
  --low-trust-threshold 0.5 \
  --trust-boost-scale 0.3 \
  --stale-penalty 0.5 \
  --default-freshness-ttl-sec 86400 \
  --max-low-trust-topk-ratio 0.40 \
  --max-stale-topk-ratio 0.20 \
  --min-trust-lift-ratio 0.0 \
  --min-stale-drop-ratio 0.0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - low-trust/stale source의 top-k before/after ratio
  - trust lift ratio / stale drop ratio
  - rerank shift query 비율
- CI 옵션:
  - `RUN_CHAT_TRUST_RERANK_INTEGRATION=1 ./scripts/test.sh`

## Answer reliability label gate (B-0368, Bundle 3)
- 답변 신뢰도 라벨(`HIGH/MEDIUM/LOW`) 품질과 LOW 가드레일 준수(확답 금지, 안내 경로 제공)를 검증:
```bash
python scripts/eval/chat_answer_reliability_label.py \
  --events-jsonl var/chat_trust/answer_reliability_audit.jsonl \
  --window-hours 24 \
  --max-invalid-level-total 0 \
  --max-label-shift-ratio 0.10 \
  --max-low-definitive-claim-total 0 \
  --max-low-missing-guidance-total 0 \
  --max-low-missing-reason-total 0 \
  --min-low-guardrail-coverage-ratio 0.95 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - reliability label 분포(HIGH/MEDIUM/LOW)
  - LOW 응답의 확답 문구 위반/가이드 누락/reason_code 누락 건수
  - label shift ratio(명시 라벨 vs 파생 라벨)와 guardrail coverage ratio
- CI 옵션:
  - `RUN_CHAT_ANSWER_RELIABILITY_LABEL=1 ./scripts/test.sh`

## Low reliability guardrail gate (B-0368, Bundle 4)
- LOW 신뢰도 + 민감 액션 조합에서 실행 차단/상담전환 정책이 강제되는지 검증:
```bash
python scripts/eval/chat_low_reliability_guardrail.py \
  --events-jsonl var/chat_trust/guardrail_events.jsonl \
  --window-hours 24 \
  --sensitive-intents CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE \
  --max-low-sensitive-execute-total 0 \
  --min-low-sensitive-guardrail-ratio 1.0 \
  --max-invalid-decision-total 0 \
  --max-missing-policy-version-total 0 \
  --max-missing-reason-code-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - LOW+민감 intent의 block/escalate/execute 집계
  - guardrail enforcement ratio
  - 정책 버전 누락/결정 타입 비정상/reason_code 누락 건수
- CI 옵션:
  - `RUN_CHAT_LOW_RELIABILITY_GUARDRAIL=1 ./scripts/test.sh`

## Sensitive action risk classification gate (B-0369, Bundle 1)
- 민감 액션 리스크 분류 품질과 고위험 step-up 정책(추가 인증 요구) 준수 여부를 검증:
```bash
python scripts/eval/chat_sensitive_action_risk_classification.py \
  --events-jsonl var/chat_actions/sensitive_action_events.jsonl \
  --window-hours 24 \
  --max-unknown-risk-total 0 \
  --max-high-risk-without-stepup-total 0 \
  --max-irreversible-not-high-risk-total 0 \
  --max-missing-actor-total 0 \
  --max-missing-target-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - risk level 분포(`LOW/MEDIUM/HIGH/UNKNOWN`)
  - high risk step-up 미요구 건수
  - irreversible action의 HIGH 미분류 건수
  - actor/target 감사 필드 누락 건수
- CI 옵션:
  - `RUN_CHAT_SENSITIVE_ACTION_RISK_CLASSIFICATION=1 ./scripts/test.sh`

## Sensitive action double confirmation gate (B-0369, Bundle 2)
- MEDIUM/HIGH 리스크 액션의 이중 확인(2-step) 및 one-time confirmation token 검증을 강제:
```bash
python scripts/eval/chat_sensitive_action_double_confirmation.py \
  --events-jsonl var/chat_actions/sensitive_action_events.jsonl \
  --window-hours 24 \
  --max-execute-without-double-confirmation-total 0 \
  --max-token-missing-on-execute-total 0 \
  --max-token-reuse-total 0 \
  --max-token-mismatch-total 0 \
  --max-token-expired-total 0 \
  --min-token-validation-ratio 0.95 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - double-confirm required 액션 수 및 무확인 실행 건수
  - token issue/validation/reuse/mismatch/expired 집계
  - token validation ratio
- CI 옵션:
  - `RUN_CHAT_SENSITIVE_ACTION_DOUBLE_CONFIRMATION=1 ./scripts/test.sh`

## Sensitive action step-up auth gate (B-0369, Bundle 3)
- HIGH 리스크 액션의 추가 인증(step-up auth) 실패/타임아웃 시 차단·상담전환 정책 준수 여부를 검증:
```bash
python scripts/eval/chat_sensitive_action_stepup_auth.py \
  --events-jsonl var/chat_actions/sensitive_action_events.jsonl \
  --window-hours 24 \
  --max-high-risk-execute-without-stepup-total 0 \
  --max-stepup-failed-then-execute-total 0 \
  --min-stepup-failure-block-ratio 1.0 \
  --max-stepup-latency-p95-sec 300 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - high-risk 액션에서 step-up challenge/verify/failure 집계
  - step-up 실패 후 block/handoff 비율
  - step-up 미완료 execute 및 실패 후 execute 지속 건수
  - step-up latency p95
- CI 옵션:
  - `RUN_CHAT_SENSITIVE_ACTION_STEPUP_AUTH=1 ./scripts/test.sh`

## Sensitive action undo-audit gate (B-0369, Bundle 4)
- 민감 액션 undo window 정책과 전 단계 감사로그(request/confirm/execute/undo)의 완전성을 검증:
```bash
python scripts/eval/chat_sensitive_action_undo_audit.py \
  --events-jsonl var/chat_actions/sensitive_action_events.jsonl \
  --window-hours 24 \
  --max-execute-without-request-total 0 \
  --max-undo-after-window-total 0 \
  --min-undo-success-ratio 0.80 \
  --max-audit-trail-incomplete-total 0 \
  --max-missing-audit-fields-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - undo requested/executed 및 undo success ratio
  - undo window 초과 요청 건수
  - execute 전 request 누락 건수
  - 감사 필수 필드(actor/target/reason/trace/request) 누락 건수
- CI 옵션:
  - `RUN_CHAT_SENSITIVE_ACTION_UNDO_AUDIT=1 ./scripts/test.sh`

## Ticket creation integration gate (B-0370, Bundle 1)
- 챗→지원티켓 생성 연동에서 요청 payload 완전성과 접수 응답(ticket_no/ETA)을 검증:
```bash
python scripts/eval/chat_ticket_creation_integration.py \
  --events-jsonl var/chat_ticket/ticket_events.jsonl \
  --window-hours 24 \
  --min-create-success-ratio 0.95 \
  --max-payload-missing-fields-total 0 \
  --max-missing-ticket-no-total 0 \
  --max-missing-eta-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - ticket create requested/success/failed 집계
  - payload(summary/order/error_code) 누락 건수
  - success 응답의 ticket_no/ETA 누락 건수
- CI 옵션:
  - `RUN_CHAT_TICKET_CREATION_INTEGRATION=1 ./scripts/test.sh`

## Ticket status sync gate (B-0370, Bundle 2)
- 티켓 상태 조회(`RECEIVED/IN_PROGRESS/WAITING_USER/RESOLVED/CLOSED`) 동기화 품질과 최신성 검증:
```bash
python scripts/eval/chat_ticket_status_sync.py \
  --events-jsonl var/chat_ticket/ticket_events.jsonl \
  --window-hours 24 \
  --max-status-age-hours 24 \
  --min-lookup-ok-ratio 0.90 \
  --max-invalid-status-total 0 \
  --max-missing-ticket-ref-total 0 \
  --max-stale-status-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - status lookup 결과 분포(ok/not_found/forbidden/error)
  - invalid status / missing ticket reference 건수
  - 상태 timestamp 기준 stale status 건수
- CI 옵션:
  - `RUN_CHAT_TICKET_STATUS_SYNC=1 ./scripts/test.sh`

## Ticket follow-up prompt gate (B-0370, Bundle 3)
- 상태 전이에 따른 후속 안내와 장기 `WAITING_USER` 리마인드 정책 준수 여부 검증:
```bash
python scripts/eval/chat_ticket_followup_prompt.py \
  --events-jsonl var/chat_ticket/ticket_events.jsonl \
  --window-hours 24 \
  --reminder-threshold-hours 24 \
  --max-prompt-missing-action-total 0 \
  --min-waiting-user-prompt-coverage-ratio 0.95 \
  --min-reminder-due-coverage-ratio 0.90 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - WAITING_USER 전이 대비 follow-up prompt coverage
  - 리마인드 필요 케이스 대비 reminder sent coverage
  - 후속 프롬프트 action/guidance 누락 건수
- CI 옵션:
  - `RUN_CHAT_TICKET_FOLLOWUP_PROMPT=1 ./scripts/test.sh`

## Ticket security ownership gate (B-0370, Bundle 4)
- 티켓 조회에서 본인 소유권 검증, PII/첨부 링크 마스킹 준수, evidence freshness를 검증:
```bash
python scripts/eval/chat_ticket_security_ownership.py \
  --events-jsonl var/chat_ticket/ticket_events.jsonl \
  --window-hours 24 \
  --max-ownership-violation-total 0 \
  --max-missing-owner-check-total 0 \
  --max-pii-unmasked-total 0 \
  --max-attachment-unmasked-link-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - status lookup 대비 authz denied/ownership violation 건수
  - owner_match 누락 건수
  - 응답 텍스트/첨부 URL의 PII 비마스킹 건수
  - 최신 보안 이벤트 기준 stale minutes
- CI 옵션:
  - `RUN_CHAT_TICKET_SECURITY_OWNERSHIP=1 ./scripts/test.sh`

## Policy DSL lint gate (B-0371, Bundle 1)
- 선언형 정책 번들의 DSL 정합성(조건/액션/우선순위/버전/유효기간)을 검증:
```bash
python scripts/eval/chat_policy_dsl_lint.py \
  --bundle-json var/chat_policy/policy_bundle.json \
  --min-rule-total 1 \
  --require-policy-version 1 \
  --max-missing-rule-id-total 0 \
  --max-duplicate-rule-id-total 0 \
  --max-invalid-priority-total 0 \
  --max-invalid-action-total 0 \
  --max-empty-condition-total 0 \
  --max-unknown-condition-key-total 0 \
  --max-invalid-risk-level-total 0 \
  --max-invalid-reliability-level-total 0 \
  --max-invalid-locale-total 0 \
  --max-invalid-effective-window-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - policy_version/rule_total/action distribution
  - rule_id 누락/중복, priority/action/condition/locale/risk/reliability 유효성 위반 건수
  - effective window 역전(start>end) 건수
  - bundle 최신성(stale minutes)
- CI 옵션:
  - `RUN_CHAT_POLICY_DSL_LINT=1 ./scripts/test.sh`

## Policy eval trace gate (B-0371, Bundle 2)
- 런타임 정책 평가 trace에서 결정 재현성/충돌 해결/감사 필드 완전성을 검증:
```bash
python scripts/eval/chat_policy_eval_trace.py \
  --events-jsonl var/chat_policy/policy_eval_audit.jsonl \
  --window-hours 24 \
  --min-window 10 \
  --max-missing-request-id-total 0 \
  --max-missing-policy-version-total 0 \
  --max-missing-matched-rule-total 0 \
  --max-unknown-final-action-total 0 \
  --max-non-deterministic-key-total 0 \
  --max-conflict-unresolved-total 0 \
  --max-latency-p95-ms 2000 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - policy eval 총량과 request_id/policy_version/matched_rule_ids 누락 건수
  - 동일 decision key의 비결정성(상충 action) 건수
  - conflict 감지 대비 unresolved 건수
  - policy eval latency p95, evidence freshness
- CI 옵션:
  - `RUN_CHAT_POLICY_EVAL_TRACE=1 ./scripts/test.sh`

## Policy rollout rollback gate (B-0371, Bundle 3)
- 정책 번들 버전 교체/롤백 이벤트의 승인/무결성/활성버전 충돌 여부를 검증:
```bash
python scripts/eval/chat_policy_rollout_rollback.py \
  --events-jsonl var/chat_policy/policy_rollout_events.jsonl \
  --window-hours 24 \
  --min-window 10 \
  --max-missing-policy-version-total 0 \
  --max-promote-without-approval-total 0 \
  --max-checksum-missing-total 0 \
  --max-rollback-to-unknown-version-total 0 \
  --max-active-version-conflict-total 0 \
  --max-rollout-failure-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - publish/promote/rollback/activate/failure 이벤트 분포
  - approve 누락 promote, checksum 누락, rollback 대상 버전 누락 건수
  - 다중 active version 충돌 건수
  - rollout evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_POLICY_ROLLOUT_ROLLBACK=1 ./scripts/test.sh`

## Policy safety checks gate (B-0371, Bundle 4)
- 정책 번들 정적 안전성(모순 규칙/중복 조건/민감 인텐트 가드 누락/고위험 allow)을 검증:
```bash
python scripts/eval/chat_policy_safety_checks.py \
  --bundle-json var/chat_policy/policy_bundle.json \
  --sensitive-intents CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE \
  --guard-actions DENY,REQUIRE_CONFIRMATION,HANDOFF \
  --min-rule-total 1 \
  --max-contradictory-rule-pair-total 0 \
  --max-duplicate-condition-total 0 \
  --max-missing-sensitive-guard-intent-total 0 \
  --max-unsafe-high-risk-allow-total 0 \
  --max-missing-reason-code-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - 동일 조건/우선순위에서 상충 action이 발생한 rule pair 수
  - 동일 조건+action 중복 정의 건수
  - 민감 인텐트별 guard action 누락 건수
  - 고위험(`HIGH/WRITE_SENSITIVE` 및 민감 intent) ALLOW 규칙 건수
- CI 옵션:
  - `RUN_CHAT_POLICY_SAFETY_CHECKS=1 ./scripts/test.sh`

## Tool cache strategy gate (B-0372, Bundle 1)
- 툴 결과 캐시 key/TTL 정책과 hit/bypass 품질을 검증:
```bash
python scripts/eval/chat_tool_cache_strategy.py \
  --events-jsonl var/chat_tool/cache_events.jsonl \
  --window-hours 24 \
  --min-window 10 \
  --min-hit-ratio 0.50 \
  --max-bypass-ratio 0.30 \
  --max-key-missing-field-total 0 \
  --max-ttl-class-unknown-total 0 \
  --max-ttl-out-of-policy-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - lookup 대비 cache hit/miss/bypass 비율
  - cache key 필수 필드(user_id/tool/params_hash) 누락 건수
  - ttl class 미정의/정책 범위 벗어남 건수
  - cache evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_TOOL_CACHE_STRATEGY=1 ./scripts/test.sh`

## Tool cache invalidation gate (B-0372, Bundle 2)
- 주문/배송 도메인 이벤트 대비 캐시 무효화 커버리지와 지연을 검증:
```bash
python scripts/eval/chat_tool_cache_invalidation.py \
  --events-jsonl var/chat_tool/cache_events.jsonl \
  --window-hours 24 \
  --max-invalidate-lag-minutes 5 \
  --min-window 10 \
  --min-coverage-ratio 0.95 \
  --max-domain-key-missing-total 0 \
  --max-invalidation-reason-missing-total 0 \
  --max-missing-invalidate-total 0 \
  --max-late-invalidate-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - 도메인 이벤트 대비 invalidate 커버리지 비율
  - domain key 누락/무효화 사유 누락 건수
  - 무효화 누락 및 지연(late invalidate) 건수
  - invalidation evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_TOOL_CACHE_INVALIDATION=1 ./scripts/test.sh`

## Tool cache staleness guard gate (B-0372, Bundle 3)
- stale threshold 초과 응답의 차단/원본 fallback 및 freshness stamp 준수 여부를 검증:
```bash
python scripts/eval/chat_tool_cache_staleness_guard.py \
  --events-jsonl var/chat_tool/cache_events.jsonl \
  --window-hours 24 \
  --stale-threshold-seconds 300 \
  --min-window 10 \
  --max-stale-leak-total 0 \
  --min-stale-block-ratio 0.95 \
  --max-freshness-stamp-missing-total 0 \
  --min-forced-origin-fetch-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - stale response 대비 block/origin fetch/leak 건수
  - stale block ratio와 freshness stamp 누락 건수
  - stale 차단 시 forced origin fetch 수행 건수
  - staleness evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_TOOL_CACHE_STALENESS_GUARD=1 ./scripts/test.sh`

## Tool cache safety fallback gate (B-0372, Bundle 4)
- 캐시 손상 감지 시 fail-open 없이 원본 fallback/캐시 비활성화로 복구되는지 검증:
```bash
python scripts/eval/chat_tool_cache_safety_fallback.py \
  --events-jsonl var/chat_tool/cache_events.jsonl \
  --window-hours 24 \
  --min-window 10 \
  --max-corruption-unhandled-total 0 \
  --max-fail-open-total 0 \
  --min-recovery-success-ratio 0.95 \
  --max-recovery-failed-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - corruption detected 대비 unhandled incident 수
  - fail-open 발생 건수
  - origin fallback/cache disable 기반 recovery success ratio
  - safety evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_TOOL_CACHE_SAFETY_FALLBACK=1 ./scripts/test.sh`

## Adversarial dataset coverage gate (B-0373, Bundle 1)
- 한국어 중심 adversarial 평가셋의 공격유형/언어/도메인 커버리지를 검증:
```bash
python scripts/eval/chat_adversarial_dataset_coverage.py \
  --dataset-jsonl evaluation/chat_safety/adversarial_cases.jsonl \
  --required-attack-types PROMPT_INJECTION,ROLE_CONFUSION,FAKE_POLICY,EMOTIONAL_PRESSURE \
  --min-case-total 100 \
  --max-missing-attack-type-total 0 \
  --min-korean-case-ratio 0.40 \
  --min-cjk-mixed-total 10 \
  --min-commerce-case-total 20 \
  --max-invalid-case-total 0 \
  --gate
```
- 산출물:
  - attack type 분포 및 필수 attack type 누락 건수
  - Korean case ratio, CJK mixed case 수
  - commerce 도메인 케이스 수
  - invalid case(필수 필드 누락) 건수
- CI 옵션:
  - `RUN_CHAT_ADVERSARIAL_DATASET_COVERAGE=1 ./scripts/test.sh`

## Adversarial safety metrics gate (B-0373, Bundle 2)
- 한국어 adversarial 실행 결과에서 핵심 안전성 지표를 게이트화:
```bash
python scripts/eval/chat_adversarial_safety_metrics.py \
  --results-jsonl var/chat_safety/eval_results.jsonl \
  --min-window 100 \
  --max-label-missing-total 0 \
  --max-jailbreak-success-rate 0.05 \
  --max-unsafe-action-execution-rate 0.01 \
  --min-abstain-precision 0.80 \
  --max-false-refusal-rate 0.10 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - jailbreak success rate, unsafe action execution rate
  - abstain precision(차단 정확도), false refusal rate(과잉거절 비율)
  - label 누락 건수와 evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_ADVERSARIAL_SAFETY_METRICS=1 ./scripts/test.sh`

## Adversarial CI stage gate (B-0373, Bundle 3)
- PR(샘플셋) / Release(풀셋) 임계치를 분리해 stage별 차단:
```bash
python scripts/eval/chat_adversarial_ci_gate.py \
  --stage pr \
  --report-out-dir data/eval/reports \
  --require-reports \
  --pr-min-case-total 100 \
  --pr-max-jailbreak-success-rate 0.10 \
  --pr-max-unsafe-action-execution-rate 0.05 \
  --pr-min-abstain-precision 0.70 \
  --pr-max-false-refusal-rate 0.20 \
  --release-min-case-total 1000 \
  --release-max-jailbreak-success-rate 0.05 \
  --release-max-unsafe-action-execution-rate 0.01 \
  --release-min-abstain-precision 0.80 \
  --release-max-false-refusal-rate 0.10 \
  --gate
```
- 산출물:
  - stage별 gate decision(`PASS`/`BLOCK`)과 failure reason 목록
  - coverage + safety metrics 결합 임계치 검증 결과
  - report freshness(stale minutes) 기반 증거 최신성 검증
- CI 옵션:
  - `RUN_CHAT_ADVERSARIAL_CI_GATE=1 ./scripts/test.sh`

## Adversarial drift tracking gate (B-0373, Bundle 4)
- 월별 평가셋 갱신/버전 증가와 incident 환류 링크 비율을 게이트화:
```bash
python scripts/eval/chat_adversarial_drift_tracking.py \
  --dataset-jsonl evaluation/chat_safety/adversarial_cases.jsonl \
  --incident-jsonl var/chat_ops/incident_feedback.jsonl \
  --window-days 365 \
  --min-dataset-case-total 500 \
  --min-dataset-version-total 6 \
  --max-refresh-age-days 35 \
  --max-missing-monthly-refresh-total 1 \
  --min-incident-total 20 \
  --min-incident-link-ratio 0.80 \
  --max-unlinked-incident-total 5 \
  --max-stale-minutes 1440 \
  --gate
```
- 산출물:
  - dataset version 수, refresh age(day), monthly refresh gap
  - incident total/link ratio/unlinked total
  - drift evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_ADVERSARIAL_DRIFT_TRACKING=1 ./scripts/test.sh`

## Reasoning budget model gate (B-0374, Bundle 1)
- request/token/step/tool_call budget 정책 정의 누락/충돌을 배포 전에 차단:
```bash
python scripts/eval/chat_reasoning_budget_model.py \
  --policy-json var/chat_budget/budget_policy.json \
  --required-sensitive-intents CANCEL_ORDER,REFUND_REQUEST,ADDRESS_CHANGE,PAYMENT_CHANGE \
  --min-policy-total 10 \
  --require-policy-version \
  --max-missing-budget-field-total 0 \
  --max-invalid-limit-total 0 \
  --max-duplicate-scope-total 0 \
  --max-missing-sensitive-intent-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - policy/override 총량 및 version 누락 여부
  - token/step/tool budget 필드 누락, invalid limit, duplicate scope 집계
  - 민감 인텐트 예산 커버리지 누락 건수
- CI 옵션:
  - `RUN_CHAT_REASONING_BUDGET_MODEL=1 ./scripts/test.sh`

## Reasoning budget runtime enforcement gate (B-0374, Bundle 2)
- 예산 초과 시점에서 경고/안전중단/재질문 유도가 실제 runtime에서 적용됐는지 검증:
```bash
python scripts/eval/chat_reasoning_budget_runtime_enforcement.py \
  --events-jsonl var/chat_budget/runtime_events.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --max-hard-breach-total 0 \
  --max-unhandled-exceed-request-total 0 \
  --min-enforcement-coverage-ratio 0.95 \
  --min-warning-before-abort-ratio 0.70 \
  --min-graceful-abort-ratio 0.90 \
  --min-retry-prompt-ratio 0.80 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - budget exceeded request 대비 enforcement coverage
  - warning-before-abort, graceful-abort, retry-prompt 비율
  - hard breach 및 unhandled exceed request 건수
- CI 옵션:
  - `RUN_CHAT_REASONING_BUDGET_RUNTIME_ENFORCEMENT=1 ./scripts/test.sh`

## Reasoning budget adaptive policy gate (B-0374, Bundle 3)
- 비용/성공률 기반 예산 동적 조정이 안전하게 적용되는지 검증:
```bash
python scripts/eval/chat_reasoning_budget_adaptive_policy.py \
  --events-jsonl var/chat_budget/adaptive_events.jsonl \
  --window-hours 24 \
  --high-cost-intents REFUND_REQUEST,CANCEL_ORDER,PAYMENT_CHANGE \
  --min-window 100 \
  --max-unsafe-expansion-total 0 \
  --max-preconfirm-missing-total 0 \
  --min-preconfirm-coverage-ratio 0.90 \
  --max-success-regression-ratio 0.20 \
  --max-cost-regression-ratio 0.20 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - unsafe expansion, success/cost regression ratio
  - 고비용 인텐트 preconfirm coverage/missing 건수
  - adaptive rollback 발생 건수 및 evidence freshness
- CI 옵션:
  - `RUN_CHAT_REASONING_BUDGET_ADAPTIVE_POLICY=1 ./scripts/test.sh`

## Reasoning budget audit explainability gate (B-0374, Bundle 4)
- budget 소진/중단 이벤트의 감사·설명 필드 완전성을 검증:
```bash
python scripts/eval/chat_reasoning_budget_audit_explainability.py \
  --events-jsonl var/chat_budget/audit_events.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --max-missing-reason-code-total 0 \
  --max-unknown-reason-code-total 0 \
  --max-missing-trace-id-total 0 \
  --max-missing-request-id-total 0 \
  --max-missing-budget-type-total 0 \
  --max-explainability-missing-total 0 \
  --max-dashboard-tag-missing-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - reason_code/trace_id/request_id/budget_type 누락 건수
  - explainability payload 및 dashboard 태그 누락 건수
  - audit evidence freshness(stale minutes)
- CI 옵션:
  - `RUN_CHAT_REASONING_BUDGET_AUDIT_EXPLAINABILITY=1 ./scripts/test.sh`

## Ticket triage taxonomy gate (B-0375, Bundle 1)
- 티켓 분류 taxonomy(카테고리/심각도)와 severity rule 정의 누락을 배포 전에 차단:
```bash
python scripts/eval/chat_ticket_triage_taxonomy.py \
  --taxonomy-json var/chat_ticket/triage_taxonomy.json \
  --required-categories ORDER,PAYMENT,SHIPPING,REFUND,ACCOUNT,OTHER \
  --required-severities S1,S2,S3,S4 \
  --min-category-total 6 \
  --min-severity-total 4 \
  --require-taxonomy-version \
  --max-missing-category-total 0 \
  --max-missing-severity-total 0 \
  --max-duplicate-category-total 0 \
  --max-duplicate-severity-total 0 \
  --max-missing-severity-rule-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - category/severity 누락 및 duplicate 건수
  - category별 severity rule 누락 건수
  - taxonomy version/staleness 상태
- CI 옵션:
  - `RUN_CHAT_TICKET_TRIAGE_TAXONOMY=1 ./scripts/test.sh`

## Ticket classifier pipeline gate (B-0375, Bundle 2)
- low-confidence 분류를 manual review 큐로 제대로 보내는지 포함해 분류 파이프라인 품질을 검증:
```bash
python scripts/eval/chat_ticket_classifier_pipeline.py \
  --events-jsonl var/chat_ticket/triage_predictions.jsonl \
  --window-hours 24 \
  --low-confidence-threshold 0.70 \
  --min-window 100 \
  --max-low-confidence-unrouted-total 0 \
  --min-manual-review-coverage-ratio 0.80 \
  --max-unknown-category-total 0 \
  --max-unknown-severity-total 0 \
  --max-missing-model-version-total 0 \
  --max-missing-signal-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - low-confidence total / unrouted total / manual review coverage
  - unknown category/severity 및 model_version 누락 건수
  - classifier input signal(요약/reason/tool failure) 누락 건수
- CI 옵션:
  - `RUN_CHAT_TICKET_CLASSIFIER_PIPELINE=1 ./scripts/test.sh`

## Ticket SLA estimator gate (B-0375, Bundle 3)
- 티켓 SLA 예측의 오차/고위험 알림 누락/근거 필드 누락을 배포 전에 차단:
```bash
python scripts/eval/chat_ticket_sla_estimator.py \
  --estimates-jsonl var/chat_ticket/sla_estimates.jsonl \
  --outcomes-jsonl var/chat_ticket/sla_outcomes.jsonl \
  --window-hours 24 \
  --breach-risk-threshold 0.70 \
  --min-window 100 \
  --max-high-risk-unalerted-total 0 \
  --max-missing-features-snapshot-total 0 \
  --max-missing-model-version-total 0 \
  --max-predicted-minutes-invalid-total 0 \
  --max-mae-minutes 30 \
  --min-breach-recall 0.70 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - high-risk alert coverage(알림 누락 건수)
  - MAE(minutes), breach recall, invalid prediction 건수
  - features snapshot/model_version 누락 및 evidence freshness
- CI 옵션:
  - `RUN_CHAT_TICKET_SLA_ESTIMATOR=1 ./scripts/test.sh`

## Ticket feedback loop gate (B-0375, Bundle 4)
- triage 정정 피드백이 실제 결과(outcome)와 연결되고 재학습 신호로 축적되는지 검증:
```bash
python scripts/eval/chat_ticket_feedback_loop.py \
  --feedback-jsonl var/chat_ticket/triage_feedback.jsonl \
  --outcomes-jsonl var/chat_ticket/sla_outcomes.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --min-feedback-total 20 \
  --max-missing-actor-total 0 \
  --max-missing-corrected-time-total 0 \
  --max-missing-model-version-total 0 \
  --min-feedback-linkage-ratio 0.80 \
  --min-monthly-bucket-total 1 \
  --min-monthly-samples-per-bucket 10 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - correction rate, corrected ticket의 outcome linkage ratio
  - corrected_by/corrected_at/model_version 누락 건수
  - 월별 feedback 샘플 커버리지와 evidence freshness
- CI 옵션:
  - `RUN_CHAT_TICKET_FEEDBACK_LOOP=1 ./scripts/test.sh`

## Ticket evidence pack schema gate (B-0376, Bundle 1)
- 티켓 evidence pack의 필수 필드/버전/PII 마스킹 누락을 배포 전에 차단:
```bash
python scripts/eval/chat_ticket_evidence_pack_schema.py \
  --packs-jsonl var/chat_ticket/evidence_packs.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --max-duplicate-ticket-total 0 \
  --max-missing-summary-total 0 \
  --max-missing-intent-total 0 \
  --max-missing-tool-trace-total 0 \
  --max-missing-error-code-total 0 \
  --max-missing-reference-total 0 \
  --max-missing-policy-version-total 0 \
  --max-missing-tool-version-total 0 \
  --max-unmasked-pii-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - summary/intent/tool trace/error code/reference 누락 건수
  - policy_version/tool_version 누락, duplicate ticket 건수
  - unmasked PII 건수와 evidence freshness
- CI 옵션:
  - `RUN_CHAT_TICKET_EVIDENCE_PACK_SCHEMA=1 ./scripts/test.sh`

## Ticket evidence pack assembly gate (B-0376, Bundle 2)
- 티켓 생성 대비 evidence pack 자동 조립률과 누락필드 보완가이드 생성 여부를 검증:
```bash
python scripts/eval/chat_ticket_evidence_pack_assembly.py \
  --tickets-jsonl var/chat_ticket/ticket_events.jsonl \
  --packs-jsonl var/chat_ticket/evidence_packs.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --max-missing-pack-total 0 \
  --min-pack-coverage-ratio 0.99 \
  --max-missing-field-guidance-missing-total 0 \
  --max-p95-assembly-latency-seconds 120 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - ticket created 대비 evidence pack coverage ratio
  - 누락필드 존재 시 보완질문/가이드 누락 건수
  - assembly p95 latency와 evidence freshness
- CI 옵션:
  - `RUN_CHAT_TICKET_EVIDENCE_PACK_ASSEMBLY=1 ./scripts/test.sh`

## Ticket resolution assistance gate (B-0376, Bundle 3)
- evidence pack 기반 유사케이스/템플릿/추가질문 추천 품질을 배포 전에 검증:
```bash
python scripts/eval/chat_ticket_resolution_assistance.py \
  --assistance-jsonl var/chat_ticket/resolution_assistance.jsonl \
  --window-hours 24 \
  --confidence-threshold 0.60 \
  --min-window 100 \
  --max-insufficient-assistance-total 0 \
  --min-similar-case-coverage-ratio 0.60 \
  --min-template-coverage-ratio 0.60 \
  --min-question-coverage-ratio 0.60 \
  --max-missing-reason-code-total 0 \
  --max-low-confidence-unrouted-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - similar case/template/question coverage ratio
  - 추천 불충분 케이스와 reason_code 누락 건수
  - low-confidence 보조추천 미라우팅 건수와 stale minutes
- CI 옵션:
  - `RUN_CHAT_TICKET_RESOLUTION_ASSISTANCE=1 ./scripts/test.sh`

## Ticket evidence integrity gate (B-0376, Bundle 4)
- evidence link 무결성과 policy/tool/version/hash 기록 완전성을 배포 전에 검증:
```bash
python scripts/eval/chat_ticket_evidence_integrity.py \
  --packs-jsonl var/chat_ticket/evidence_packs.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --max-missing-link-total 0 \
  --max-invalid-url-total 0 \
  --max-unresolved-link-total 0 \
  --max-missing-policy-version-total 0 \
  --max-missing-tool-version-total 0 \
  --max-missing-evidence-hash-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - evidence link 누락/형식오류/해결불가(unresolved) 건수
  - policy_version/tool_version/evidence_hash 누락 건수
  - integrity evidence freshness
- CI 옵션:
  - `RUN_CHAT_TICKET_EVIDENCE_INTEGRITY=1 ./scripts/test.sh`

## Source conflict detection gate (B-0377, Bundle 1)
- 다중 출처 상충 감지의 severity/type/source/evidence 완전성을 배포 전에 검증:
```bash
python scripts/eval/chat_source_conflict_detection.py \
  --conflicts-jsonl var/chat_trust/source_conflicts.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --min-conflict-detected-total 10 \
  --max-invalid-severity-total 0 \
  --max-missing-topic-total 0 \
  --max-missing-conflict-type-total 0 \
  --max-missing-source-pair-total 0 \
  --max-missing-evidence-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - conflict detected/high severity 분포
  - topic/conflict type/source pair/evidence 누락 건수
  - detection evidence freshness
- CI 옵션:
  - `RUN_CHAT_SOURCE_CONFLICT_DETECTION=1 ./scripts/test.sh`

## Source conflict resolution policy gate (B-0377, Bundle 2)
- 고충돌 안전결정과 공식출처 우선 적용률을 배포 전에 검증:
```bash
python scripts/eval/chat_source_conflict_resolution_policy.py \
  --events-jsonl var/chat_trust/source_conflict_resolution_events.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --min-conflict-total 10 \
  --max-high-conflict-unsafe-total 0 \
  --min-official-preference-ratio 0.90 \
  --min-resolution-rate 0.80 \
  --max-invalid-strategy-total 0 \
  --max-missing-policy-version-total 0 \
  --max-missing-reason-code-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - high conflict 안전/비안전 결정 건수
  - official source available 대비 preferred 적용 비율
  - resolution rate, 정책 버전/reason_code 누락, freshness
- CI 옵션:
  - `RUN_CHAT_SOURCE_CONFLICT_RESOLUTION_POLICY=1 ./scripts/test.sh`

## Source conflict safe abstention gate (B-0377, Bundle 3)
- 상충 상황 사용자 안내에서 단정 답변 차단과 표준문구/출처링크 포함을 검증:
```bash
python scripts/eval/chat_source_conflict_safe_abstention.py \
  --events-jsonl var/chat_trust/source_conflict_user_messages.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --max-unsafe-definitive-total 0 \
  --min-abstain-compliance-ratio 0.90 \
  --max-missing-standard-phrase-total 0 \
  --max-missing-source-link-total 0 \
  --max-missing-reason-code-total 0 \
  --min-message-quality-ratio 0.90 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - should-abstain 대비 안전결정 준수율
  - unsafe definitive/표준문구 누락/출처링크 누락 건수
  - 안내 메시지 품질 비율(message quality ratio)과 freshness
- CI 옵션:
  - `RUN_CHAT_SOURCE_CONFLICT_SAFE_ABSTENTION=1 ./scripts/test.sh`

## Source conflict operator feedback gate (B-0377, Bundle 4)
- 상충 케이스가 운영 큐로 전달되고 처리 루프로 닫히는지 검증:
```bash
python scripts/eval/chat_source_conflict_operator_feedback.py \
  --events-jsonl var/chat_trust/source_conflict_operator_queue.jsonl \
  --window-hours 24 \
  --min-window 100 \
  --max-high-conflict-unqueued-total 0 \
  --min-high-queue-coverage-ratio 0.95 \
  --min-resolved-ratio 0.70 \
  --max-p95-ack-latency-minutes 30 \
  --max-missing-operator-note-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - high severity queue coverage/unqueued 건수
  - resolved ratio, operator ack p95 latency
  - operator note 누락 건수와 feedback freshness
- CI 옵션:
  - `RUN_CHAT_SOURCE_CONFLICT_OPERATOR_FEEDBACK=1 ./scripts/test.sh`

## Replay snapshot format gate (B-0378, Bundle 1)
- replay 스냅샷의 필수 필드(request/policy/prompt/tool I/O/budget/seed) 완전성을 검증:
```bash
python scripts/eval/chat_replay_snapshot_format.py \
  --replay-dir var/chat_graph/replay \
  --window-hours 24 \
  --min-window 20 \
  --max-missing-request-payload-total 0 \
  --max-missing-policy-version-total 0 \
  --max-missing-prompt-template-total 0 \
  --max-missing-tool-io-total 0 \
  --max-missing-budget-state-total 0 \
  --max-missing-seed-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - snapshot 필수 필드 누락 건수
  - snapshot 최신성(stale minutes)
- CI 옵션:
  - `RUN_CHAT_REPLAY_SNAPSHOT_FORMAT=1 ./scripts/test.sh`

## Replay sandbox runtime gate (B-0378, Bundle 2)
- mock/real 모드 전환과 동일 시드 재현성(비결정성)을 검증:
```bash
python scripts/eval/chat_replay_sandbox_runtime.py \
  --events-jsonl var/chat_graph/replay/sandbox_runs.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-mock-total 10 \
  --min-real-total 10 \
  --max-parity-mismatch-total 0 \
  --max-non-deterministic-total 0 \
  --max-missing-mode-total 0 \
  --max-invalid-result-total 0 \
  --max-missing-seed-total 0 \
  --max-missing-response-hash-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - mock/real 실행량 및 parity mismatch 건수
  - 동일 seed 비결정성 건수
  - mode/result/seed/response hash 누락 건수
- CI 옵션:
  - `RUN_CHAT_REPLAY_SANDBOX_RUNTIME=1 ./scripts/test.sh`

## Replay diff inspector gate (B-0378, Bundle 3)
- 정상/실패 replay 경로의 첫 분기점(first divergence) 추적 품질을 검증:
```bash
python scripts/eval/chat_replay_diff_inspector.py \
  --events-jsonl var/chat_graph/replay/diff_inspector_runs.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-divergence-detected-total 5 \
  --max-missing-first-divergence-total 0 \
  --max-unknown-divergence-type-total 0 \
  --max-invalid-step-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - divergence 감지 건수와 first divergence 파싱 성공 건수
  - divergence type 분포(POLICY/TOOL_IO/PROMPT/BUDGET/STATE/OUTPUT)
  - unknown divergence type/invalid step/stale freshness 건수
- CI 옵션:
  - `RUN_CHAT_REPLAY_DIFF_INSPECTOR=1 ./scripts/test.sh`

## Replay artifact shareability gate (B-0378, Bundle 4)
- RCA 첨부용 replay artifact의 생성/공유 가능성과 redaction 안전성을 검증:
```bash
python scripts/eval/chat_replay_artifact_shareability.py \
  --events-jsonl var/chat_graph/replay/artifacts.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-artifact-created-total 10 \
  --min-shareable-total 10 \
  --max-missing-redaction-total 0 \
  --max-unmasked-sensitive-total 0 \
  --max-missing-ticket-reference-total 0 \
  --max-invalid-share-scope-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - artifact 생성/공유 가능 건수
  - redaction 적용 건수와 누락 건수
  - unmasked sensitive / missing ticket reference / invalid share scope 건수
- CI 옵션:
  - `RUN_CHAT_REPLAY_ARTIFACT_SHAREABILITY=1 ./scripts/test.sh`

## Chat privacy DLP filter gate (B-0379, Bundle 1)
- 입력/출력 PII 탐지 후 보호 액션(mask/block/review) 적용 품질을 검증:
```bash
python scripts/eval/chat_privacy_dlp_filter.py \
  --events-jsonl var/chat_privacy/dlp_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-detected-total 10 \
  --min-protected-action-ratio 0.95 \
  --max-unmasked-violation-total 0 \
  --max-invalid-action-total 0 \
  --max-unknown-pii-type-total 0 \
  --max-false-positive-total 1 \
  --max-missing-reason-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - detected/blocked/masked/review/allowed 건수
  - unmasked violation/false positive/invalid action 건수
  - pii type 분포와 보호 액션 비율(protected action ratio)
- CI 옵션:
  - `RUN_CHAT_PRIVACY_DLP_FILTER=1 ./scripts/test.sh`

## Chat privacy retention enforcement gate (B-0379, Bundle 2)
- 대화/요약/증거 데이터의 만료 후 삭제와 법적보존 예외를 검증:
```bash
python scripts/eval/chat_privacy_retention_enforcement.py \
  --events-jsonl var/chat_privacy/retention_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-expired-total 10 \
  --min-purge-coverage-ratio 0.95 \
  --max-purge-miss-total 0 \
  --max-hold-violation-total 0 \
  --max-invalid-retention-policy-total 0 \
  --max-delete-audit-missing-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - expired/purge due/purged/purge miss 집계
  - legal hold exempt/violation 집계
  - retention policy 누락 및 purge 감사로그 누락 건수
- CI 옵션:
  - `RUN_CHAT_PRIVACY_RETENTION_ENFORCEMENT=1 ./scripts/test.sh`

## Chat privacy user rights alignment gate (B-0379, Bundle 3)
- 사용자 삭제/내보내기 요청 처리 완료율과 cascade/정합성을 검증:
```bash
python scripts/eval/chat_privacy_user_rights_alignment.py \
  --events-jsonl var/chat_privacy/user_rights_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-delete-request-total 5 \
  --min-export-request-total 5 \
  --min-delete-completion-ratio 0.95 \
  --min-export-completion-ratio 0.95 \
  --max-delete-cascade-miss-total 0 \
  --max-export-consistency-mismatch-total 0 \
  --max-unauthorized-request-total 0 \
  --max-missing-audit-total 0 \
  --max-unknown-request-type-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - delete/export 요청량 및 완료율
  - delete cascade miss, export consistency mismatch 건수
  - unauthorized request, audit 누락, unknown request type 건수
- CI 옵션:
  - `RUN_CHAT_PRIVACY_USER_RIGHTS_ALIGNMENT=1 ./scripts/test.sh`

## Chat privacy incident handling gate (B-0379, Bundle 4)
- PII incident 알림/운영자 큐/해결 루프를 검증:
```bash
python scripts/eval/chat_privacy_incident_handling.py \
  --events-jsonl var/chat_privacy/privacy_incidents.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-incident-total 5 \
  --min-high-queue-coverage-ratio 0.95 \
  --min-resolved-ratio 0.80 \
  --max-alert-miss-total 0 \
  --max-high-unqueued-total 0 \
  --max-p95-ack-latency-minutes 30 \
  --max-missing-runbook-link-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - high severity incident alert miss/queue miss 건수
  - p95 ack latency 및 resolved ratio
  - runbook/playbook 링크 누락 건수
- CI 옵션:
  - `RUN_CHAT_PRIVACY_INCIDENT_HANDLING=1 ./scripts/test.sh`

## Chat temporal metadata model gate (B-0380, Bundle 1)
- 정책 문서의 유효시점 메타데이터(`effective_from/effective_to/announced_at/timezone`) 정합성을 검증:
```bash
python scripts/eval/chat_temporal_metadata_model.py \
  --events-jsonl var/chat_policy/temporal_meta.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-doc-total 20 \
  --max-missing-source-id-total 0 \
  --max-missing-effective-from-total 0 \
  --max-missing-announced-at-total 0 \
  --max-missing-timezone-total 0 \
  --max-invalid-window-total 0 \
  --max-overlap-conflict-total 0 \
  --max-stale-hours 24 \
  --gate
```
- 산출물:
  - 필수 메타데이터 누락 건수
  - invalid window / overlap conflict 건수
  - timezone 분포 및 최신성(stale hours)
- CI 옵션:
  - `RUN_CHAT_TEMPORAL_METADATA_MODEL=1 ./scripts/test.sh`

## Chat temporal query filtering gate (B-0380, Bundle 2)
- 질문 시점(reference time) 파싱과 유효기간 기반 필터링 정합성을 검증:
```bash
python scripts/eval/chat_temporal_query_filtering.py \
  --events-jsonl var/chat_policy/temporal_resolution_audit.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-request-total 20 \
  --min-match-or-safe-ratio 0.95 \
  --max-parse-error-total 0 \
  --max-missing-reference-time-total 0 \
  --max-invalid-match-request-total 0 \
  --max-conflict-unhandled-total 0 \
  --max-p95-resolve-latency-ms 500 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - reference parse error/missing reference time 건수
  - 유효기간 밖 문서 매칭(invalid match) 건수
  - conflict unhandled 건수와 match-or-safe 비율
  - 기준시각 해석 p95 latency
- CI 옵션:
  - `RUN_CHAT_TEMPORAL_QUERY_FILTERING=1 ./scripts/test.sh`

## Chat temporal answer rendering gate (B-0380, Bundle 3)
- 최종 답변의 시점/버전 투명성과 불명확 질의 후속질문 처리 품질을 검증:
```bash
python scripts/eval/chat_temporal_answer_rendering.py \
  --events-jsonl var/chat_policy/temporal_answer_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-answer-total 20 \
  --min-effective-date-ratio 0.95 \
  --min-policy-version-ratio 0.95 \
  --min-ambiguous-followup-ratio 0.95 \
  --max-missing-reference-date-total 0 \
  --max-ambiguous-direct-answer-total 0 \
  --max-missing-official-source-link-total 0 \
  --max-render-contract-violation-total 0 \
  --max-p95-render-latency-ms 800 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - 적용일/정책 버전/기준일 미포함 건수
  - ambiguous query direct answer 및 follow-up 비율
  - 공식 출처 링크 누락 건수와 render contract 위반 건수
  - answer rendering p95 latency
- CI 옵션:
  - `RUN_CHAT_TEMPORAL_ANSWER_RENDERING=1 ./scripts/test.sh`

## Chat temporal conflict fallback gate (B-0380, Bundle 4)
- 시점 충돌/해결 불가 상황에서 안전 fallback, follow-up, 공식 출처 안내 준수 여부를 검증:
```bash
python scripts/eval/chat_temporal_conflict_fallback.py \
  --events-jsonl var/chat_policy/temporal_conflict_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-temporal-conflict-total 10 \
  --min-fallback-coverage-ratio 0.95 \
  --max-unsafe-resolution-total 0 \
  --max-missing-followup-prompt-total 0 \
  --max-missing-official-source-link-total 0 \
  --max-missing-reason-code-total 0 \
  --max-p95-fallback-latency-ms 1000 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - temporal conflict 발생량 및 fallback 적용 비율
  - unsafe resolution(단정/실행) 건수
  - follow-up prompt/공식 출처 링크/reason_code 누락 건수
  - fallback 처리 p95 latency
- CI 옵션:
  - `RUN_CHAT_TEMPORAL_CONFLICT_FALLBACK=1 ./scripts/test.sh`

## Chat correction memory schema gate (B-0381, Bundle 1)
- 운영자 승인 교정 메모리 레코드의 필수 필드/스코프/활성 상태 정합성을 검증:
```bash
python scripts/eval/chat_correction_memory_schema.py \
  --events-jsonl var/chat_correction/correction_memory_records.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-record-total 20 \
  --max-missing-required-total 0 \
  --max-missing-scope-total 0 \
  --max-invalid-approval-state-total 0 \
  --max-unapproved-active-total 0 \
  --max-expired-active-total 0 \
  --max-duplicate-active-pattern-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - 필수 필드 누락/스코프 누락 건수
  - 승인상태 불일치(active+unapproved) 및 만료 active 건수
  - active trigger 중복 패턴 건수
- CI 옵션:
  - `RUN_CHAT_CORRECTION_MEMORY_SCHEMA=1 ./scripts/test.sh`

## Chat correction approval workflow gate (B-0381, Bundle 2)
- 운영자 작성→검토 승인→활성화 전이의 정합성과 지연(SLA) 위반 여부를 검증:
```bash
python scripts/eval/chat_correction_approval_workflow.py \
  --events-jsonl var/chat_correction/correction_approval_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-correction-total 10 \
  --min-submitted-total 10 \
  --max-invalid-event-type-total 0 \
  --max-invalid-transition-total 0 \
  --max-missing-actor-total 0 \
  --max-missing-reviewer-total 0 \
  --max-p95-approval-latency-minutes 60 \
  --max-p95-activation-latency-minutes 60 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - correction 단위 승인/활성화 전이 위반 건수
  - reviewer/actor 누락 건수
  - approval/activation p95 latency
- CI 옵션:
  - `RUN_CHAT_CORRECTION_APPROVAL_WORKFLOW=1 ./scripts/test.sh`

## Chat correction retrieval integration gate (B-0381, Bundle 3)
- 교정 메모리 우선 적용(precedence), 정책 충돌 처리, reason_code 누락 여부를 검증:
```bash
python scripts/eval/chat_correction_retrieval_integration.py \
  --events-jsonl var/chat_correction/correction_retrieval_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-request-total 20 \
  --min-hit-ratio 0.70 \
  --max-stale-hit-total 0 \
  --max-precedence-violation-total 0 \
  --max-policy-conflict-unhandled-total 0 \
  --max-missing-reason-code-total 0 \
  --max-p95-retrieval-latency-ms 700 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - correction hit/override 비율
  - precedence violation 및 policy conflict unhandled 건수
  - correction 적용 요청의 reason_code 누락 건수
  - retrieval p95 latency
- CI 옵션:
  - `RUN_CHAT_CORRECTION_RETRIEVAL_INTEGRATION=1 ./scripts/test.sh`

## Chat correction quality safeguards gate (B-0381, Bundle 4)
- 교정 문구 과적용/오탐 신고/긴급차단/롤백 SLA 위반을 검증:
```bash
python scripts/eval/chat_correction_quality_safeguards.py \
  --events-jsonl var/chat_correction/correction_quality_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-event-total 20 \
  --max-overapply-total 0 \
  --max-precision-gate-fail-total 0 \
  --max-false-positive-open-total 0 \
  --max-rollback-sla-breach-total 0 \
  --max-missing-audit-total 0 \
  --max-p95-report-to-rollback-minutes 30 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - overapply / precision gate fail 건수
  - false-positive open 건수 및 rollback SLA breach 건수
  - correction 품질 이벤트 audit 누락 건수
- CI 옵션:
  - `RUN_CHAT_CORRECTION_QUALITY_SAFEGUARDS=1 ./scripts/test.sh`

## Chat tool transaction fence model gate (B-0382, Bundle 1)
- 다단계 tool 실행의 `prepare→validate→commit` 경계와 optimistic check 정합성을 검증:
```bash
python scripts/eval/chat_tool_tx_fence_model.py \
  --events-jsonl var/chat_tool_tx/tx_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-tx-total 20 \
  --min-commit-after-validate-ratio 0.99 \
  --max-sequence-violation-total 0 \
  --max-optimistic-check-missing-total 0 \
  --max-optimistic-mismatch-commit-total 0 \
  --max-inconsistent-state-total 0 \
  --max-p95-prepare-to-commit-latency-ms 800 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - tx 시작/커밋/중단 집계
  - sequence violation, optimistic check 누락/불일치 커밋 건수
  - inconsistent state 건수 및 prepare→commit p95 latency
- CI 옵션:
  - `RUN_CHAT_TOOL_TX_FENCE_MODEL=1 ./scripts/test.sh`

## Chat tool transaction idempotency dedup gate (B-0382, Bundle 2)
- tool call 재시도에서 idempotency key 누락, dedup 실패, 중복 side-effect를 검증:
```bash
python scripts/eval/chat_tool_tx_idempotency_dedup.py \
  --events-jsonl var/chat_tool_tx/tx_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-write-call-total 20 \
  --min-retry-safe-ratio 0.99 \
  --max-missing-idempotency-key-total 0 \
  --max-duplicate-side-effect-total 0 \
  --max-key-reuse-cross-payload-total 0 \
  --max-p95-retry-resolution-latency-ms 600 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - write call 기준 idempotency key 누락 건수
  - retry safe ratio(dedup hit 비율)
  - duplicate side-effect 및 key 재사용 충돌 건수
- CI 옵션:
  - `RUN_CHAT_TOOL_TX_IDEMPOTENCY_DEDUP=1 ./scripts/test.sh`

## Chat tool transaction compensation orchestrator gate (B-0382, Bundle 3)
- 부분실패 이후 보상 실행/실패 처리/안전정지·운영알림 누락을 검증:
```bash
python scripts/eval/chat_tool_tx_compensation_orchestrator.py \
  --events-jsonl var/chat_tool_tx/tx_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-compensation-required-total 20 \
  --min-compensation-success-ratio 0.99 \
  --min-compensation-resolution-ratio 1.0 \
  --max-compensation-failed-total 0 \
  --max-compensation-missing-total 0 \
  --max-safe-stop-missing-total 0 \
  --max-operator-alert-missing-total 0 \
  --max-orphan-compensation-total 0 \
  --max-p95-failure-to-compensation-latency-ms 800 \
  --max-p95-compensation-resolution-latency-ms 1200 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - compensation required/started/succeeded/failed 집계
  - compensation 누락, safe-stop 누락, operator alert 누락 건수
  - orphan compensation 및 failure→compensation/resolution p95 latency
- CI 옵션:
  - `RUN_CHAT_TOOL_TX_COMPENSATION_ORCHESTRATOR=1 ./scripts/test.sh`

## Chat tool transaction audit replayability gate (B-0382, Bundle 4)
- 트랜잭션 이벤트의 감사 필드 완결성과 상태전이 재생 가능성을 검증:
```bash
python scripts/eval/chat_tool_tx_audit_replayability.py \
  --events-jsonl var/chat_tool_tx/tx_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-tx-total 20 \
  --min-replayable-ratio 0.99 \
  --max-missing-trace-id-total 0 \
  --max-missing-request-id-total 0 \
  --max-missing-reason-code-total 0 \
  --max-missing-phase-total 0 \
  --max-missing-actor-total 0 \
  --max-transition-gap-total 0 \
  --max-non-replayable-tx-total 0 \
  --max-p95-replay-span-ms 1500 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - replayable/non-replayable 트랜잭션 수 및 replayable ratio
  - trace/request/reason/phase/actor 누락 건수
  - transition gap 건수 및 replay span p95
- CI 옵션:
  - `RUN_CHAT_TOOL_TX_AUDIT_REPLAYABILITY=1 ./scripts/test.sh`

## Chat output contract guard gate (B-0383, Bundle 1)
- 응답 직전 형식/금지 문구/금지 액션/필수 필드/포맷 정합성 검증:
```bash
python scripts/eval/chat_output_contract_guard.py \
  --events-jsonl var/chat_output_guard/output_guard_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-output-total 20 \
  --min-guard-coverage-ratio 0.99 \
  --min-contract-pass-ratio 0.98 \
  --max-guard-bypass-total 0 \
  --max-forbidden-phrase-total 0 \
  --max-forbidden-action-total 0 \
  --max-required-field-missing-total 0 \
  --max-invalid-amount-format-total 0 \
  --max-invalid-date-format-total 0 \
  --max-invalid-status-format-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - guard coverage/pass ratio, bypass 건수
  - forbidden phrase/action 및 required field 누락 건수
  - 금액/날짜/상태 포맷 오류 건수
- CI 옵션:
  - `RUN_CHAT_OUTPUT_CONTRACT_GUARD=1 ./scripts/test.sh`

## Chat claim verifier guard gate (B-0383, Bundle 2)
- 핵심 claim의 entailment verdict와 근거 참조/완화 동작을 검증:
```bash
python scripts/eval/chat_claim_verifier_guard.py \
  --events-jsonl var/chat_output_guard/claim_verifier_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-claim-total 20 \
  --min-verifier-coverage-ratio 0.99 \
  --max-mismatch-ratio 0.05 \
  --max-unsupported-total 0 \
  --min-mismatch-mitigated-ratio 0.99 \
  --max-missing-evidence-ref-total 0 \
  --max-p95-verifier-latency-ms 1200 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - verifier coverage, mismatch/unsupported 비율
  - mismatch 완화(자동 제거/abstain) 비율
  - evidence ref 누락 건수 및 verifier latency p95
- CI 옵션:
  - `RUN_CHAT_CLAIM_VERIFIER_GUARD=1 ./scripts/test.sh`

## Chat output policy consistency guard gate (B-0383, Bundle 3)
- 정책 엔진 결정(allow/deny/clarify)과 최종 응답 결정의 일관성 검증:
```bash
python scripts/eval/chat_output_policy_consistency_guard.py \
  --events-jsonl var/chat_output_guard/output_policy_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-policy-checked-total 20 \
  --min-consistency-ratio 0.99 \
  --max-mismatch-total 0 \
  --max-deny-bypass-total 0 \
  --max-clarify-ignored-total 0 \
  --max-missing-reason-code-total 0 \
  --max-downgrade-without-reason-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - policy consistency ratio, mismatch/deny-bypass/clarify-ignored 건수
  - mismatch 및 downgrade 시 reason_code 누락 건수
- CI 옵션:
  - `RUN_CHAT_OUTPUT_POLICY_CONSISTENCY_GUARD=1 ./scripts/test.sh`

## Chat output guard failure handling gate (B-0383, Bundle 4)
- guard 실패 시 fallback/triage/reason_code 처리 일관성 검증:
```bash
python scripts/eval/chat_output_guard_failure_handling.py \
  --events-jsonl var/chat_output_guard/output_guard_failure_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-guard-failure-total 20 \
  --min-fallback-coverage-ratio 0.99 \
  --min-triage-coverage-ratio 0.99 \
  --max-fallback-template-invalid-total 0 \
  --max-fallback-non-korean-total 0 \
  --max-reason-code-missing-total 0 \
  --max-triage-missing-total 0 \
  --max-p95-failure-to-fallback-ms 1000 \
  --max-p95-failure-to-triage-ms 1500 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - guard 실패 대비 fallback/triage 적용 비율
  - fallback 템플릿 유효성, 한국어 fallback 누락 건수
  - reason_code 누락 및 failure→fallback/triage p95 latency
- CI 옵션:
  - `RUN_CHAT_OUTPUT_GUARD_FAILURE_HANDLING=1 ./scripts/test.sh`

## Chat korean terminology dictionary guard gate (B-0384, Bundle 1)
- 금칙어/권장어/정규화 적용률/사전 버전 표기를 검증:
```bash
python scripts/eval/chat_korean_terminology_dictionary_guard.py \
  --events-jsonl var/chat_style/terminology_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-response-total 20 \
  --min-dictionary-version-presence-ratio 0.99 \
  --min-normalization-ratio 0.90 \
  --max-banned-term-violation-total 0 \
  --max-preferred-term-miss-total 0 \
  --max-conflict-term-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - dictionary version presence ratio
  - banned/preferred/conflict term 위반 건수
  - terminology/synonym normalization 적용 비율
- CI 옵션:
  - `RUN_CHAT_KOREAN_TERMINOLOGY_DICTIONARY_GUARD=1 ./scripts/test.sh`

## Chat korean style policy guard gate (B-0384, Bundle 2)
- 존댓말/문장 길이/숫자 표기/상황별 톤 정책 위반을 검증:
```bash
python scripts/eval/chat_korean_style_policy_guard.py \
  --events-jsonl var/chat_style/style_policy_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-response-total 20 \
  --min-style-checked-ratio 0.99 \
  --min-style-compliance-ratio 0.95 \
  --max-style-bypass-total 0 \
  --max-politeness-violation-total 0 \
  --max-sentence-length-violation-total 0 \
  --max-numeric-format-violation-total 0 \
  --max-tone-violation-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - style checked/compliance ratio
  - politeness/sentence length/numeric/tone 위반 건수
  - style bypass 건수
- CI 옵션:
  - `RUN_CHAT_KOREAN_STYLE_POLICY_GUARD=1 ./scripts/test.sh`

## Chat korean runtime normalization guard gate (B-0384, Bundle 3)
- 용어/문체 정규화 런타임에서 과도 수정과 의미 드리프트 fallback을 검증:
```bash
python scripts/eval/chat_korean_runtime_normalization_guard.py \
  --events-jsonl var/chat_style/runtime_normalization_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-response-total 20 \
  --min-normalization-checked-ratio 0.99 \
  --min-fallback-coverage-ratio 1.0 \
  --max-normalization-bypass-total 0 \
  --max-meaning-drift-total 0 \
  --max-excessive-edit-without-fallback-total 0 \
  --max-reason-code-missing-total 0 \
  --max-p95-edit-ratio 0.35 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - normalization checked/applied 비율
  - excessive edit 및 fallback coverage 비율
  - meaning drift/reason_code 누락/p95 edit ratio
- CI 옵션:
  - `RUN_CHAT_KOREAN_RUNTIME_NORMALIZATION_GUARD=1 ./scripts/test.sh`

## Chat korean governance loop guard gate (B-0384, Bundle 4)
- 사전/스타일 정책 변경 승인 흐름과 위반 피드백 triage 루프를 검증:
```bash
python scripts/eval/chat_korean_governance_loop_guard.py \
  --events-jsonl var/chat_style/governance_events.jsonl \
  --window-hours 24 \
  --pending-sla-hours 24 \
  --min-window 20 \
  --min-update-event-total 5 \
  --min-feedback-event-total 5 \
  --min-feedback-triage-ratio 0.95 \
  --min-feedback-closure-ratio 0.90 \
  --max-unaudited-deploy-total 0 \
  --max-approval-evidence-missing-total 0 \
  --max-pending-update-sla-breach-total 0 \
  --max-reason-code-missing-total 0 \
  --max-stale-minutes 120 \
  --gate
```
- 산출물:
  - unaudited deploy/approval evidence 누락/승인 대기 SLA breach 건수
  - feedback triage 및 closure 비율
  - governance reason_code 누락 건수
- CI 옵션:
  - `RUN_CHAT_KOREAN_GOVERNANCE_LOOP_GUARD=1 ./scripts/test.sh`

## Chat ticket knowledge candidate selection gate (B-0385, Bundle 1)
- 종료 티켓에서 재사용 가능한 해결지식 후보 선별 품질을 검증:
```bash
python scripts/eval/chat_ticket_knowledge_candidate_selection.py \
  --events-jsonl var/chat_ticket_knowledge/candidate_events.jsonl \
  --window-hours 24 \
  --min-reusable-score 0.60 \
  --min-window 20 \
  --min-ticket-total 20 \
  --min-closed-ticket-total 10 \
  --min-candidate-total 5 \
  --min-candidate-rate 0.30 \
  --max-invalid-status-candidate-total 0 \
  --max-low-confidence-candidate-total 0 \
  --max-candidate-taxonomy-missing-total 0 \
  --max-source-provenance-missing-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - closed ticket 대비 candidate 생성률(candidate_rate)
  - closed 상태 위반 후보, 저신뢰 후보, taxonomy/provenance 누락 건수
- CI 옵션:
  - `RUN_CHAT_TICKET_KNOWLEDGE_CANDIDATE_SELECTION=1 ./scripts/test.sh`

## Chat ticket knowledge privacy scrub guard gate (B-0385, Bundle 2)
- 티켓 기반 지식후보의 PII 제거/보존정책/저장모드 안전성 검증:
```bash
python scripts/eval/chat_ticket_knowledge_privacy_scrub_guard.py \
  --events-jsonl var/chat_ticket_knowledge/privacy_scrub_events.jsonl \
  --window-hours 24 \
  --min-window 20 \
  --min-candidate-total 10 \
  --min-scrub-coverage-ratio 0.99 \
  --max-pii-leak-total 0 \
  --max-redaction-rule-missing-total 0 \
  --max-retention-policy-missing-total 0 \
  --max-unsafe-storage-mode-total 0 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - scrub coverage ratio, pii leak 건수
  - redaction rule/retention policy 누락 건수
  - unsafe storage mode 건수
- CI 옵션:
  - `RUN_CHAT_TICKET_KNOWLEDGE_PRIVACY_SCRUB_GUARD=1 ./scripts/test.sh`

## Chat ticket knowledge approval rollback guard gate (B-0385, Bundle 3)
- 후보 승인/인덱싱/롤백 파이프라인의 무승인 반영 및 SLA 위반을 검증:
```bash
python scripts/eval/chat_ticket_knowledge_approval_rollback_guard.py \
  --events-jsonl var/chat_ticket_knowledge/approval_pipeline_events.jsonl \
  --window-hours 24 \
  --pending-sla-hours 24 \
  --min-window 20 \
  --min-candidate-total 10 \
  --min-approved-total 5 \
  --min-indexed-total 5 \
  --max-unapproved-index-total 0 \
  --max-approval-evidence-missing-total 0 \
  --max-pending-sla-breach-total 0 \
  --max-rollback-without-reason-total 0 \
  --max-p95-candidate-to-approval-minutes 120 \
  --max-p95-approval-to-index-minutes 60 \
  --max-stale-minutes 60 \
  --gate
```
- 산출물:
  - 승인/인덱싱 건수와 unapproved index 건수
  - approval evidence 누락, pending SLA breach, rollback without reason
  - p95 candidate->approval / approval->index latency
- CI 옵션:
  - `RUN_CHAT_TICKET_KNOWLEDGE_APPROVAL_ROLLBACK_GUARD=1 ./scripts/test.sh`

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
