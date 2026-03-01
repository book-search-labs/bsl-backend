package com.bsl.search.service;

import com.bsl.search.api.dto.BookHit;
import com.bsl.search.api.dto.BookDetailResponse;
import com.bsl.search.api.dto.Options;
import com.bsl.search.api.dto.QueryContext;
import com.bsl.search.api.dto.QueryContextV1_1;
import com.bsl.search.api.dto.SearchRequest;
import com.bsl.search.api.dto.SearchResponse;
import com.bsl.search.cache.BookDetailCacheService;
import com.bsl.search.cache.SerpCacheService;
import com.bsl.search.experiment.SearchExperimentProperties;
import com.bsl.search.merge.RrfFusion;
import com.bsl.search.merge.WeightedFusion;
import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.query.QueryServiceGateway;
import com.bsl.search.query.QueryServiceProperties;
import com.bsl.search.query.QueryServiceUnavailableException;
import com.bsl.search.query.dto.QueryEnhanceRequest;
import com.bsl.search.query.dto.QueryEnhanceResponse;
import com.bsl.search.retrieval.FusionMethod;
import com.bsl.search.retrieval.FusionPolicyProperties;
import com.bsl.search.retrieval.LexicalRetriever;
import com.bsl.search.retrieval.RetrievalStageContext;
import com.bsl.search.retrieval.RetrievalStageResult;
import com.bsl.search.retrieval.VectorRetriever;
import com.bsl.search.service.grouping.MaterialGroupingService;
import com.bsl.search.resilience.CircuitBreaker;
import com.bsl.search.resilience.SearchResilienceRegistry;
import com.bsl.search.ranking.RankingGateway;
import com.bsl.search.ranking.RankingUnavailableException;
import com.bsl.search.ranking.dto.RerankRequest;
import com.bsl.search.ranking.dto.RerankResponse;
import com.fasterxml.jackson.databind.JsonNode;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Random;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class HybridSearchService {
    private static final Logger log = LoggerFactory.getLogger(HybridSearchService.class);
    private static final int DEFAULT_SIZE = 10;
    private static final int DEFAULT_FROM = 0;
    private static final int DEFAULT_RRF_K = 60;
    private static final int DEFAULT_LEX_TOP_K = 200;
    private static final int DEFAULT_VEC_TOP_K = 200;
    private static final int MIN_TOP_K = 10;
    private static final int MAX_TOP_K = 500;
    private static final int MIN_TIME_BUDGET_MS = 50;
    private static final int MAX_TIME_BUDGET_MS = 1000;
    private static final int DEFAULT_QC_LEX_TOP_K = 300;
    private static final int DEFAULT_QC_VEC_TOP_K = 200;
    private static final int DEFAULT_QC_RERANK_TOP_K = 50;
    private static final int DEFAULT_QC_TIMEOUT_MS = 120;
    private static final int QC_LEX_TOP_K_MIN = 50;
    private static final int QC_LEX_TOP_K_MAX = 1000;
    private static final int QC_VEC_TOP_K_MIN = 20;
    private static final int QC_VEC_TOP_K_MAX = 500;
    private static final int QC_RRF_K_MIN = 10;
    private static final int QC_RRF_K_MAX = 200;
    private static final int QC_RERANK_TOP_K_MIN = 10;
    private static final int QC_RERANK_TOP_K_MAX = 200;
    private static final int QC_TIMEOUT_MIN_MS = 50;
    private static final int QC_TIMEOUT_MAX_MS = 500;

    private final OpenSearchGateway openSearchGateway;
    private final LexicalRetriever lexicalRetriever;
    private final VectorRetriever vectorRetriever;
    private final FusionPolicyProperties fusionPolicy;
    private final RankingGateway rankingGateway;
    private final SearchResilienceRegistry resilienceRegistry;
    private final SerpCacheService serpCacheService;
    private final BookDetailCacheService bookDetailCacheService;
    private final ExecutorService searchExecutor;
    private final SearchExperimentProperties experimentProperties;
    private final MaterialGroupingService groupingService;
    private final RerankPolicyProperties rerankPolicy;
    private final SearchBudgetProperties budgetProperties;
    private final SearchQualityEvaluator qualityEvaluator;
    private final QueryServiceGateway queryServiceGateway;
    private final QueryServiceProperties queryServiceProperties;
    private final MeterRegistry meterRegistry;
    private static final Pattern ISBN_PATTERN = Pattern.compile("^(97(8|9))?\\d{9}[\\dXx]$");

    public HybridSearchService(
        OpenSearchGateway openSearchGateway,
        LexicalRetriever lexicalRetriever,
        VectorRetriever vectorRetriever,
        FusionPolicyProperties fusionPolicy,
        RankingGateway rankingGateway,
        SearchResilienceRegistry resilienceRegistry,
        SerpCacheService serpCacheService,
        BookDetailCacheService bookDetailCacheService,
        ExecutorService searchExecutor,
        SearchExperimentProperties experimentProperties,
        MaterialGroupingService groupingService,
        RerankPolicyProperties rerankPolicy,
        SearchBudgetProperties budgetProperties,
        SearchQualityEvaluator qualityEvaluator,
        QueryServiceGateway queryServiceGateway,
        QueryServiceProperties queryServiceProperties,
        MeterRegistry meterRegistry
    ) {
        this.openSearchGateway = openSearchGateway;
        this.lexicalRetriever = lexicalRetriever;
        this.vectorRetriever = vectorRetriever;
        this.fusionPolicy = fusionPolicy;
        this.rankingGateway = rankingGateway;
        this.resilienceRegistry = resilienceRegistry;
        this.serpCacheService = serpCacheService;
        this.bookDetailCacheService = bookDetailCacheService;
        this.searchExecutor = searchExecutor;
        this.experimentProperties = experimentProperties;
        this.groupingService = groupingService;
        this.rerankPolicy = rerankPolicy;
        this.budgetProperties = budgetProperties;
        this.qualityEvaluator = qualityEvaluator;
        this.queryServiceGateway = queryServiceGateway;
        this.queryServiceProperties = queryServiceProperties;
        this.meterRegistry = meterRegistry;
    }

    public SearchResponse search(SearchRequest request, String traceId, String requestId, String traceparent) {
        if (request == null) {
            throw new InvalidSearchRequestException("request body is required");
        }
        if (request.getQueryContextV1_1() != null) {
            return searchWithQcV11(request, traceId, requestId, traceparent);
        }
        return searchLegacy(request, traceId, requestId, traceparent);
    }

    public BookDetailResult getBookById(String docId, String traceId, String requestId) {
        long started = System.nanoTime();
        if (bookDetailCacheService.isEnabled()) {
            Optional<BookDetailCacheService.CachedBook> cached = bookDetailCacheService.get(docId);
            if (cached.isPresent()) {
                BookDetailCacheService.CachedBook entry = cached.get();
                BookDetailResponse cachedResponse = copyBookDetailResponse(
                    entry.getResponse(),
                    traceId,
                    requestId,
                    (System.nanoTime() - started) / 1_000_000L
                );
                long ageMs = Math.max(0L, System.currentTimeMillis() - entry.getCreatedAt());
                long ttlMs = Math.max(0L, entry.getExpiresAt() - entry.getCreatedAt());
                return new BookDetailResult(
                    cachedResponse,
                    entry.getEtag(),
                    true,
                    ageMs,
                    ttlMs,
                    bookDetailCacheService.getCacheControlMaxAgeSeconds()
                );
            }
        }

        JsonNode source = openSearchGateway.getSourceById(docId);
        if (source == null || source.isMissingNode()) {
            return null;
        }

        String resolvedDocId = source.path("doc_id").asText(null);
        if (resolvedDocId == null || resolvedDocId.isBlank()) {
            resolvedDocId = docId;
        }

        BookDetailResponse response = new BookDetailResponse();
        response.setDocId(resolvedDocId);
        response.setSource(mapSource(source, resolvedDocId));
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs((System.nanoTime() - started) / 1_000_000L);

        if (bookDetailCacheService.isEnabled()) {
            bookDetailCacheService.put(resolvedDocId, response);
        }
        String etag = bookDetailCacheService.computeEtag(response);
        return new BookDetailResult(
            response,
            etag,
            false,
            0L,
            bookDetailCacheService.getTtlMs(),
            bookDetailCacheService.getCacheControlMaxAgeSeconds()
        );
    }

    private SearchResponse searchLegacy(
        SearchRequest request,
        String traceId,
        String requestId,
        String traceparent
    ) {
        long started = System.nanoTime();

        Options options = request.getOptions() == null ? new Options() : request.getOptions();
        int size = options.getSize() != null ? Math.max(options.getSize(), 0) : DEFAULT_SIZE;
        int from = options.getFrom() != null ? Math.max(options.getFrom(), 0) : DEFAULT_FROM;
        ExecutionPlan plan = buildLegacyPlan(request, options);
        plan.rerankTopK = Math.min(Math.max(from + size, DEFAULT_SIZE), plan.lexicalTopK);
        applyRerankTopKGuardrail(plan);
        if (isBlank(plan.queryText)) {
            throw new InvalidSearchRequestException("query text is required");
        }
        assignExperimentBucket(plan, requestId);

        String cacheKey = buildSerpCacheKey(plan, from, size);
        Optional<SearchResponse> cachedResponse = maybeServeSerpCache(cacheKey, traceId, requestId, started, plan);
        if (cachedResponse.isPresent()) {
            return cachedResponse.get();
        }

        RetrievalResult retrieval = retrieveCandidates(plan, traceId, requestId);
        RerankOutcome rerankOutcome = applyRerank(
            plan,
            retrieval,
            from,
            size,
            traceId,
            requestId,
            traceparent
        );

        SearchResponse.Debug debug = buildDebug(
            plan,
            retrieval,
            rerankOutcome,
            null,
            cacheKey,
            false,
            EnhanceOutcome.notAttempted()
        );
        List<BookHit> finalHits = maybeApplyExploration(plan, rerankOutcome.hits, from, size, requestId, debug);
        finalHits = groupingService.apply(plan.queryText, finalHits, size);
        SearchResponse response = buildResponse(
            started,
            traceId,
            requestId,
            finalHits,
            retrieval.fused == null ? finalHits.size() : retrieval.fused.size(),
            rerankOutcome.rankingApplied,
            resolveLegacyStrategy(plan),
            debug
        );
        response.setExperimentBucket(plan.experimentBucket);

        if (shouldStoreSerpCache(plan, response, cacheKey)) {
            serpCacheService.put(cacheKey, stripDebug(response));
        }

        if (response.getHits() == null || response.getHits().isEmpty()) {
            Optional<SearchResponse> degraded = maybeServeSerpCache(cacheKey, traceId, requestId, started, plan, true);
            if (degraded.isPresent()) {
                return degraded.get();
            }
        }
        return response;
    }

    private SearchResponse searchWithQcV11(
        SearchRequest request,
        String traceId,
        String requestId,
        String traceparent
    ) {
        long started = System.nanoTime();

        QueryContextV1_1 qc = request.getQueryContextV1_1();
        if (qc.getMeta() == null || qc.getMeta().getSchemaVersion() == null
            || !"qc.v1.1".equals(qc.getMeta().getSchemaVersion())) {
            throw new InvalidSearchRequestException("query_context_v1_1.meta.schemaVersion must be qc.v1.1");
        }

        Options options = request.getOptions() == null ? new Options() : request.getOptions();
        int size = options.getSize() != null ? Math.max(options.getSize(), 0) : DEFAULT_SIZE;
        int from = options.getFrom() != null ? Math.max(options.getFrom(), 0) : DEFAULT_FROM;

        ExecutionPlan plan = buildPlanFromQcV11(qc, options);
        if (isBlank(plan.queryText)
            && (plan.filters == null || plan.filters.isEmpty())
            && (plan.lexicalQueryOverride == null || plan.lexicalQueryOverride.isEmpty())) {
            throw new InvalidSearchRequestException("query text is required");
        }
        assignExperimentBucket(plan, requestId);

        String appliedFallbackId = null;
        String cacheKey = buildSerpCacheKey(plan, from, size);
        Optional<SearchResponse> cachedResponse = maybeServeSerpCache(cacheKey, traceId, requestId, started, plan);
        if (cachedResponse.isPresent()) {
            return cachedResponse.get();
        }

        RetrievalResult retrieval = retrieveCandidates(plan, traceId, requestId);

        if (retrieval.vector.isError() || retrieval.vector.isTimedOut()) {
            FallbackApplication fallback = applyFallback(plan, Trigger.VECTOR_ERROR);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(plan, traceId, requestId);
            }
        }

        if (retrieval.fused.isEmpty() && appliedFallbackId == null) {
            FallbackApplication fallback = applyFallback(plan, Trigger.ZERO_RESULTS);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(plan, traceId, requestId);
            }
        }

        EnhanceOutcome enhanceOutcome = maybeRetryWithEnhance(
            plan,
            qc,
            retrieval,
            started,
            traceId,
            requestId,
            traceparent
        );
        if (enhanceOutcome.retryRetrieval != null) {
            retrieval = enhanceOutcome.retryRetrieval;
        }

        RerankOutcome rerankOutcome = applyRerank(
            plan,
            retrieval,
            from,
            size,
            traceId,
            requestId,
            traceparent
        );

        if (rerankOutcome.rerankError && appliedFallbackId == null) {
            FallbackApplication fallback = applyFallback(plan, Trigger.RERANK_ERROR);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(plan, traceId, requestId);
                rerankOutcome = applyRerank(
                    plan,
                    retrieval,
                    from,
                    size,
                    traceId,
                    requestId,
                    traceparent
                );
            }
        }

        String strategy = resolveQcStrategy(plan, appliedFallbackId);
        SearchResponse.Debug debug = buildDebug(
            plan,
            retrieval,
            rerankOutcome,
            appliedFallbackId,
            cacheKey,
            false,
            enhanceOutcome
        );
        List<BookHit> finalHits = maybeApplyExploration(plan, rerankOutcome.hits, from, size, requestId, debug);
        finalHits = groupingService.apply(plan.queryText, finalHits, size);

        SearchResponse response = buildResponse(
            started,
            traceId,
            requestId,
            finalHits,
            retrieval.fused == null ? finalHits.size() : retrieval.fused.size(),
            rerankOutcome.rankingApplied,
            strategy,
            debug
        );
        response.setExperimentBucket(plan.experimentBucket);

        if (shouldStoreSerpCache(plan, response, cacheKey)) {
            serpCacheService.put(cacheKey, stripDebug(response));
        }

        if (response.getHits() == null || response.getHits().isEmpty()) {
            Optional<SearchResponse> degraded = maybeServeSerpCache(cacheKey, traceId, requestId, started, plan, true);
            if (degraded.isPresent()) {
                return degraded.get();
            }
        }
        return response;
    }

    private Map<String, Integer> rankMap(List<String> docIds) {
        Map<String, Integer> ranks = new HashMap<>();
        for (int i = 0; i < docIds.size(); i++) {
            String docId = docIds.get(i);
            if (!ranks.containsKey(docId)) {
                ranks.put(docId, i + 1);
            }
        }
        return ranks;
    }

    private List<String> toDocIds(List<RrfFusion.Candidate> candidates) {
        List<String> docIds = new ArrayList<>(candidates.size());
        for (RrfFusion.Candidate candidate : candidates) {
            docIds.add(candidate.getDocId());
        }
        return docIds;
    }

    private Map<String, RrfFusion.Candidate> toCandidateMap(List<RrfFusion.Candidate> candidates) {
        Map<String, RrfFusion.Candidate> byId = new HashMap<>();
        for (RrfFusion.Candidate candidate : candidates) {
            byId.put(candidate.getDocId(), candidate);
        }
        return byId;
    }

    private List<RerankRequest.Candidate> buildRerankCandidates(
        List<RrfFusion.Candidate> candidates,
        Map<String, JsonNode> sources
    ) {
        List<RerankRequest.Candidate> rerankCandidates = new ArrayList<>(candidates.size());
        for (RrfFusion.Candidate candidate : candidates) {
            RerankRequest.Candidate rerankCandidate = new RerankRequest.Candidate();
            rerankCandidate.setDocId(candidate.getDocId());

            RerankRequest.Features features = new RerankRequest.Features();
            features.setLexRank(candidate.getLexRank());
            features.setVecRank(candidate.getVecRank());
            features.setRrfScore(candidate.getScore());
            features.setFusedRank(candidate.getFusedRank());
            features.setRrfRank(candidate.getFusedRank());
            features.setBm25Score(candidate.getBm25Score());
            features.setVecScore(candidate.getVecScore());

            JsonNode source = sources.get(candidate.getDocId());
            rerankCandidate.setDoc(buildDocText(candidate.getDocId(), source));
            if (source != null && !source.isMissingNode()) {
                rerankCandidate.setTitle(readTitle(source));
                rerankCandidate.setAuthors(extractAuthors(source));
                rerankCandidate.setSeries(readText(source, "series_name"));
                rerankCandidate.setPublisher(readText(source, "publisher_name"));
                features.setIssuedYear(readInteger(source, "issued_year"));
                features.setVolume(readInteger(source, "volume"));
                features.setEditionLabels(extractEditionLabels(source));
            } else {
                rerankCandidate.setAuthors(Collections.emptyList());
                features.setEditionLabels(Collections.emptyList());
            }

            rerankCandidate.setFeatures(features);
            rerankCandidates.add(rerankCandidate);
        }
        return rerankCandidates;
    }

    private List<BookHit> buildHitsFromRanking(
        List<RerankResponse.Hit> rankHits,
        Map<String, RrfFusion.Candidate> fusedById,
        int from,
        int size,
        Map<String, JsonNode> sources
    ) {
        int total = rankHits.size();
        int startIndex = Math.min(from, total);
        int endIndex = Math.min(startIndex + size, total);

        List<BookHit> hits = new ArrayList<>(Math.max(endIndex - startIndex, 0));
        for (int i = startIndex; i < endIndex; i++) {
            RerankResponse.Hit rerankHit = rankHits.get(i);
            String docId = rerankHit.getDocId();
            if (docId == null || docId.isEmpty()) {
                continue;
            }
            RrfFusion.Candidate candidate = fusedById.get(docId);

            BookHit hit = new BookHit();
            hit.setDocId(docId);
            hit.setScore(rerankHit.getScore());
            hit.setRank(i + 1);

            BookHit.Debug debug = new BookHit.Debug();
            if (candidate != null) {
                debug.setLexRank(candidate.getLexRank());
                debug.setVecRank(candidate.getVecRank());
                debug.setRrfScore(candidate.getScore());
            }
            debug.setRankingScore(rerankHit.getScore());
            hit.setDebug(debug);
            hit.setSource(mapSource(sources.get(docId), docId));
            hits.add(hit);
        }
        return hits;
    }

    private List<BookHit> buildHitsFromFused(
        List<RrfFusion.Candidate> fused,
        int from,
        int size,
        Map<String, JsonNode> sources
    ) {
        int total = fused.size();
        int startIndex = Math.min(from, total);
        int endIndex = Math.min(startIndex + size, total);

        List<BookHit> hits = new ArrayList<>(Math.max(endIndex - startIndex, 0));
        for (int i = startIndex; i < endIndex; i++) {
            RrfFusion.Candidate candidate = fused.get(i);
            BookHit hit = new BookHit();
            hit.setDocId(candidate.getDocId());
            hit.setScore(candidate.getScore());
            hit.setRank(i + 1);

            BookHit.Debug debug = new BookHit.Debug();
            debug.setLexRank(candidate.getLexRank());
            debug.setVecRank(candidate.getVecRank());
            debug.setRrfScore(candidate.getScore());
            hit.setDebug(debug);

            hit.setSource(mapSource(sources.get(candidate.getDocId()), candidate.getDocId()));
            hits.add(hit);
        }
        return hits;
    }

    private RetrievalResult retrieveCandidates(ExecutionPlan plan, String traceId, String requestId) {
        RetrievalStageResult lexicalResult = RetrievalStageResult.empty();
        RetrievalStageResult vectorResult = RetrievalStageResult.empty();

        RetrievalStageContext lexicalContext = new RetrievalStageContext(
            plan.queryText,
            plan.lexicalTopK,
            plan.boost,
            plan.lexicalBudgetMs != null ? plan.lexicalBudgetMs : plan.timeBudgetMs,
            plan.lexicalOperator,
            plan.minimumShouldMatch,
            plan.filters,
            plan.lexicalFields,
            plan.lexicalQueryOverride,
            plan.debugEnabled,
            plan.explainEnabled,
            traceId,
            requestId
        );

        RetrievalStageContext vectorContext = new RetrievalStageContext(
            plan.queryText,
            plan.vectorTopK,
            null,
            plan.vectorBudgetMs != null ? plan.vectorBudgetMs : plan.timeBudgetMs,
            null,
            null,
            plan.filters,
            null,
            null,
            plan.debugEnabled,
            plan.explainEnabled,
            traceId,
            requestId
        );

        CompletableFuture<RetrievalStageResult> lexicalFuture = plan.lexicalEnabled
            ? CompletableFuture.supplyAsync(() -> lexicalRetriever.retrieve(lexicalContext), searchExecutor)
            : CompletableFuture.completedFuture(RetrievalStageResult.empty());

        CompletableFuture<RetrievalStageResult> vectorFuture;
        CircuitBreaker vectorBreaker = resilienceRegistry.getVectorBreaker();
        if (!plan.vectorEnabled) {
            vectorFuture = CompletableFuture.completedFuture(RetrievalStageResult.skipped("vector_disabled"));
        } else if (!vectorBreaker.allowRequest()) {
            vectorFuture = CompletableFuture.completedFuture(RetrievalStageResult.skipped("vector_circuit_open"));
        } else {
            vectorFuture = CompletableFuture.supplyAsync(() -> vectorRetriever.retrieve(vectorContext), searchExecutor);
        }

        lexicalResult = awaitStage(lexicalFuture, plan.lexicalBudgetMs != null ? plan.lexicalBudgetMs : plan.timeBudgetMs);
        vectorResult = awaitStage(vectorFuture, plan.vectorBudgetMs != null ? plan.vectorBudgetMs : plan.timeBudgetMs);

        if (plan.vectorEnabled && !vectorResult.isSkipped()) {
            if (vectorResult.isError() || vectorResult.isTimedOut()) {
                vectorBreaker.recordFailure();
            } else {
                vectorBreaker.recordSuccess();
            }
        }

        Map<String, Integer> lexRanks = rankMap(lexicalResult.getDocIds());
        Map<String, Integer> vecRanks = rankMap(vectorResult.getDocIds());
        Map<String, Double> lexScores = lexicalResult.getScoresByDocId();
        Map<String, Double> vecScores = vectorResult.getScoresByDocId();

        long fusionStarted = System.nanoTime();
        FusionMethod fusionMethod = resolveFusionMethod(plan, requestId);
        List<RrfFusion.Candidate> fused = fuseCandidates(lexRanks, vecRanks, lexScores, vecScores, plan, fusionMethod);
        long fusionTookMs = (System.nanoTime() - fusionStarted) / 1_000_000L;

        List<String> fusedDocIds = toDocIds(fused);
        Map<String, JsonNode> sources;
        if (fusedDocIds.isEmpty()) {
            sources = Collections.emptyMap();
        } else {
            try {
                sources = openSearchGateway.mgetSources(fusedDocIds, plan.timeBudgetMs);
            } catch (RuntimeException e) {
                sources = Collections.emptyMap();
            }
        }
        if (shouldPrioritizeKoreanTitles(plan)) {
            fused = prioritizeKoreanTitles(fused, sources);
        }

        return new RetrievalResult(fused, sources, lexicalResult, vectorResult, fusionTookMs);
    }

    private boolean shouldPrioritizeKoreanTitles(ExecutionPlan plan) {
        if (plan == null) {
            return false;
        }
        if (isSingleTokenHangulQuery(plan.queryText)) {
            return true;
        }
        return isBlank(plan.queryText) && containsKdcFilter(plan.filters);
    }

    private boolean isSingleTokenHangulQuery(String queryText) {
        String normalized = trimToNull(queryText);
        if (normalized == null) {
            return false;
        }
        if (normalized.split("\\s+").length != 1) {
            return false;
        }
        return containsHangul(normalized);
    }

    private boolean containsKdcFilter(List<Map<String, Object>> filters) {
        if (filters == null || filters.isEmpty()) {
            return false;
        }
        for (Map<String, Object> filter : filters) {
            if (containsKdcFilterNode(filter)) {
                return true;
            }
        }
        return false;
    }

    @SuppressWarnings("unchecked")
    private boolean containsKdcFilterNode(Object node) {
        if (node instanceof Map<?, ?> raw) {
            Map<Object, Object> map = (Map<Object, Object>) raw;
            Object term = map.get("term");
            if (term instanceof Map<?, ?> termMap && hasKdcField(termMap)) {
                return true;
            }
            Object terms = map.get("terms");
            if (terms instanceof Map<?, ?> termsMap && hasKdcField(termsMap)) {
                return true;
            }
            for (Object value : map.values()) {
                if (containsKdcFilterNode(value)) {
                    return true;
                }
            }
            return false;
        }
        if (node instanceof List<?> list) {
            for (Object item : list) {
                if (containsKdcFilterNode(item)) {
                    return true;
                }
            }
            return false;
        }
        return false;
    }

    private boolean hasKdcField(Map<?, ?> map) {
        for (Object key : map.keySet()) {
            if (key instanceof String text && text.toLowerCase(Locale.ROOT).startsWith("kdc_")) {
                return true;
            }
        }
        return false;
    }

    private List<RrfFusion.Candidate> prioritizeKoreanTitles(List<RrfFusion.Candidate> fused, Map<String, JsonNode> sources) {
        if (fused == null || fused.isEmpty() || sources == null || sources.isEmpty()) {
            return fused;
        }
        List<RrfFusion.Candidate> korean = new ArrayList<>();
        List<RrfFusion.Candidate> other = new ArrayList<>();
        for (RrfFusion.Candidate candidate : fused) {
            JsonNode source = sources.get(candidate.getDocId());
            String title = readText(source, "title_ko");
            if (containsHangul(title)) {
                korean.add(candidate);
            } else {
                other.add(candidate);
            }
        }
        if (korean.isEmpty() || other.isEmpty()) {
            return fused;
        }
        List<RrfFusion.Candidate> reordered = new ArrayList<>(fused.size());
        reordered.addAll(korean);
        reordered.addAll(other);
        return reordered;
    }

    private boolean containsHangul(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if ((ch >= 0x1100 && ch <= 0x11FF)
                || (ch >= 0x3130 && ch <= 0x318F)
                || (ch >= 0xA960 && ch <= 0xA97F)
                || (ch >= 0xD7B0 && ch <= 0xD7FF)
                || (ch >= 0xAC00 && ch <= 0xD7AF)) {
                return true;
            }
        }
        return false;
    }

    private EnhanceOutcome maybeRetryWithEnhance(
        ExecutionPlan plan,
        QueryContextV1_1 qc,
        RetrievalResult retrieval,
        long started,
        String traceId,
        String requestId,
        String traceparent
    ) {
        int hitCount = retrieval == null || retrieval.fused == null ? 0 : retrieval.fused.size();
        double topScore = topScore(retrieval);
        SearchQualityEvaluator.QualityEvaluation quality = qualityEvaluator.evaluate(hitCount, topScore);
        if (!quality.shouldEnhance()) {
            return EnhanceOutcome.notAttempted();
        }
        if (plan.lexicalQueryOverride != null && !plan.lexicalQueryOverride.isEmpty()) {
            return EnhanceOutcome.skipped(quality.getReason(), "EXPLICIT_FIELD_ROUTING");
        }

        String qNorm = resolveQNorm(qc, plan.queryText);
        if (isBlank(qNorm)) {
            return EnhanceOutcome.skipped(quality.getReason(), "MISSING_QUERY_TEXT");
        }
        if (isIsbnQuery(qc, qNorm)) {
            return EnhanceOutcome.skipped(quality.getReason(), "ISBN_QUERY");
        }

        int remainingBudgetMs = estimateRemainingBudget(plan, started);
        if (remainingBudgetMs <= 0) {
            return EnhanceOutcome.skipped(quality.getReason(), "BUDGET_EXHAUSTED");
        }

        meterRegistry.counter("sr_enhance_attempt_total", "reason", quality.getReason()).increment();
        QueryEnhanceRequest enhanceRequest = buildEnhanceRequest(
            qc,
            qNorm,
            quality,
            hitCount,
            topScore,
            remainingBudgetMs,
            traceId,
            requestId,
            plan.debugEnabled
        );
        int timeoutMs = Math.min(remainingBudgetMs, queryServiceProperties.getTimeoutMs());
        EnhanceOutcome outcome = EnhanceOutcome.attempted(quality.getReason());
        long callStarted = System.nanoTime();
        QueryEnhanceResponse response;
        try {
            response = queryServiceGateway.enhance(
                enhanceRequest,
                timeoutMs,
                traceId,
                requestId,
                traceparent
            );
        } catch (QueryServiceUnavailableException ex) {
            outcome.skipReason = "QS_TIMEOUT_OR_ERROR";
            recordEnhanceLatency(callStarted);
            log.info(
                "sr_enhance trace_id={} request_id={} reason={} strategy=NONE final_source=NONE improved=false skip_reason={}",
                traceId,
                requestId,
                quality.getReason(),
                outcome.skipReason
            );
            return outcome;
        }
        recordEnhanceLatency(callStarted);

        if (response == null) {
            outcome.skipReason = "EMPTY_ENHANCE_RESPONSE";
            return outcome;
        }

        outcome.decision = response.getDecision();
        outcome.strategy = response.getStrategy();
        if (!"RUN".equalsIgnoreCase(response.getDecision()) || response.getFinalQuery() == null) {
            outcome.skipReason = "ENHANCE_SKIP";
            log.info(
                "sr_enhance trace_id={} request_id={} reason={} strategy={} final_source=NONE improved=false skip_reason={}",
                traceId,
                requestId,
                quality.getReason(),
                response.getStrategy(),
                outcome.skipReason
            );
            return outcome;
        }

        String finalQuery = trimToNull(response.getFinalQuery().getText());
        if (isBlank(finalQuery)) {
            outcome.skipReason = "EMPTY_FINAL_QUERY";
            return outcome;
        }

        plan.queryText = finalQuery;
        plan.queryTextSourceUsed = "query.enhance";
        meterRegistry.counter("sr_search_retry_total").increment();
        RetrievalResult retryResult = retrieveCandidates(plan, traceId, requestId);

        boolean improved = isEnhancedImproved(retrieval, retryResult);
        meterRegistry.counter("sr_enhance_success_total", "improved", Boolean.toString(improved)).increment();

        outcome.applied = true;
        outcome.finalQuery = finalQuery;
        outcome.finalSource = response.getFinalQuery().getSource();
        outcome.improved = improved;
        outcome.retryRetrieval = retryResult;
        log.info(
            "sr_enhance trace_id={} request_id={} reason={} strategy={} final_source={} improved={}",
            traceId,
            requestId,
            quality.getReason(),
            response.getStrategy(),
            outcome.finalSource == null ? "unknown" : outcome.finalSource,
            improved
        );
        return outcome;
    }

    private QueryEnhanceRequest buildEnhanceRequest(
        QueryContextV1_1 qc,
        String qNorm,
        SearchQualityEvaluator.QualityEvaluation quality,
        int hits,
        double topScore,
        int remainingBudgetMs,
        String traceId,
        String requestId,
        boolean debugEnabled
    ) {
        QueryEnhanceRequest request = new QueryEnhanceRequest();
        request.setTraceId(traceId);
        request.setRequestId(requestId);
        request.setQNorm(qNorm);
        request.setQNospace(resolveQNoSpace(qc, qNorm));
        request.setReason(quality.getReason());
        request.setLocale(resolveLocale(qc));
        request.setDebug(debugEnabled);

        Map<String, Object> signals = new HashMap<>();
        signals.put("hits", hits);
        signals.put("top_score", topScore);
        signals.put("from", 0);
        signals.put("size", DEFAULT_SIZE);
        signals.put("latency_budget_ms", remainingBudgetMs);
        request.setSignals(signals);

        request.setDetected(buildDetectedPayload(qc));
        return request;
    }

    private Map<String, Object> buildDetectedPayload(QueryContextV1_1 qc) {
        if (qc == null || qc.getDetected() == null) {
            return Map.of();
        }
        Map<String, Object> detected = new HashMap<>();
        if (qc.getDetected().getMode() != null) {
            detected.put("mode", qc.getDetected().getMode());
        }
        if (qc.getDetected().getIsIsbn() != null) {
            detected.put("is_isbn", qc.getDetected().getIsIsbn());
            detected.put("isIsbn", qc.getDetected().getIsIsbn());
        }
        return detected;
    }

    private String resolveQNorm(QueryContextV1_1 qc, String fallback) {
        if (qc != null && qc.getQuery() != null) {
            if (!isBlank(qc.getQuery().getNorm())) {
                return qc.getQuery().getNorm().trim();
            }
            if (!isBlank(qc.getQuery().getFinalValue())) {
                return qc.getQuery().getFinalValue().trim();
            }
        }
        return trimToNull(fallback);
    }

    private String resolveQNoSpace(QueryContextV1_1 qc, String qNorm) {
        if (qc != null && qc.getQuery() != null && !isBlank(qc.getQuery().getNospace())) {
            return qc.getQuery().getNospace().trim();
        }
        return qNorm == null ? null : qNorm.replaceAll("\\s+", "");
    }

    private String resolveLocale(QueryContextV1_1 qc) {
        if (qc != null && qc.getMeta() != null && !isBlank(qc.getMeta().getLocale())) {
            return qc.getMeta().getLocale().trim();
        }
        return "ko-KR";
    }

    private int estimateRemainingBudget(ExecutionPlan plan, long started) {
        if (plan == null || plan.timeBudgetMs == null) {
            return queryServiceProperties.getTimeoutMs();
        }
        long elapsed = Math.max(0L, (System.nanoTime() - started) / 1_000_000L);
        return Math.max(0, (int) (plan.timeBudgetMs - elapsed));
    }

    private boolean isIsbnQuery(QueryContextV1_1 qc, String qNorm) {
        if (qc != null && qc.getDetected() != null && Boolean.TRUE.equals(qc.getDetected().getIsIsbn())) {
            return true;
        }
        if (qNorm == null) {
            return false;
        }
        String compact = qNorm.replaceAll("[^0-9Xx]", "");
        return ISBN_PATTERN.matcher(compact).matches();
    }

    private void recordEnhanceLatency(long started) {
        long tookMs = Math.max(0L, (System.nanoTime() - started) / 1_000_000L);
        Timer.builder("sr_enhance_latency_ms").register(meterRegistry).record(tookMs, TimeUnit.MILLISECONDS);
    }

    private double topScore(RetrievalResult retrieval) {
        if (retrieval == null || retrieval.fused == null || retrieval.fused.isEmpty()) {
            return 0.0d;
        }
        return retrieval.fused.get(0).getScore();
    }

    private boolean isEnhancedImproved(RetrievalResult before, RetrievalResult after) {
        int beforeHits = before == null || before.fused == null ? 0 : before.fused.size();
        int afterHits = after == null || after.fused == null ? 0 : after.fused.size();
        if (beforeHits == 0 && afterHits > 0) {
            return true;
        }
        if (afterHits > beforeHits) {
            return true;
        }
        double beforeTop = topScore(before);
        double afterTop = topScore(after);
        return afterTop > beforeTop;
    }

    private List<RrfFusion.Candidate> fuseCandidates(
        Map<String, Integer> lexRanks,
        Map<String, Integer> vecRanks,
        Map<String, Double> lexScores,
        Map<String, Double> vecScores,
        ExecutionPlan plan,
        FusionMethod method
    ) {
        int k = plan.rrfK;
        if (method == FusionMethod.WEIGHTED) {
            double lexWeight = fusionPolicy == null ? 1.0 : fusionPolicy.getLexWeight();
            double vecWeight = fusionPolicy == null ? 1.0 : fusionPolicy.getVecWeight();
            return WeightedFusion.fuse(lexRanks, vecRanks, k, lexWeight, vecWeight, lexScores, vecScores);
        }
        return RrfFusion.fuse(lexRanks, vecRanks, k, lexScores, vecScores);
    }

    private FusionMethod resolveFusionMethod(ExecutionPlan plan, String requestId) {
        FusionMethod fromPlan = plan == null ? null : plan.fusionMethod;
        if (fromPlan != null) {
            return fromPlan;
        }
        if (fusionPolicy == null) {
            if (plan != null) {
                plan.fusionMethod = FusionMethod.RRF;
            }
            return FusionMethod.RRF;
        }
        if (fusionPolicy.isExperimentEnabled() && requestId != null) {
            double rate = Math.max(0.0, fusionPolicy.getWeightedRate());
            if (rate > 0.0 && hashToUnitInterval(requestId) < rate) {
                if (plan != null) {
                    plan.fusionMethod = FusionMethod.WEIGHTED;
                }
                return FusionMethod.WEIGHTED;
            }
        }
        FusionMethod configured = FusionMethod.fromString(fusionPolicy.getDefaultMethod());
        FusionMethod resolved = configured == null ? FusionMethod.RRF : configured;
        if (plan != null) {
            plan.fusionMethod = resolved;
        }
        return resolved;
    }

    private String shouldSkipRerank(ExecutionPlan plan, RetrievalResult retrieval) {
        if (plan == null) {
            return "rerank_plan_missing";
        }
        if (!plan.rerankEnabled) {
            return "rerank_disabled";
        }
        if (retrieval == null || retrieval.fused.isEmpty()) {
            return "rerank_no_candidates";
        }
        if (plan.rerankTopK <= 0) {
            return "rerank_topk_zero";
        }
        if (rerankPolicy != null && !rerankPolicy.isEnabled()) {
            return "rerank_policy_disabled";
        }
        if (rerankPolicy != null) {
            if (rerankPolicy.isSkipIsbn() && isIsbnQuery(plan.queryText)) {
                return "rerank_skipped_isbn";
            }
            int minQueryLength = rerankPolicy.getMinQueryLength();
            if (minQueryLength > 0 && (plan.queryText == null || plan.queryText.trim().length() < minQueryLength)) {
                return "rerank_skipped_short_query";
            }
            int minCandidates = rerankPolicy.getMinCandidates();
            if (minCandidates > 0 && retrieval.fused.size() < minCandidates) {
                return "rerank_skipped_min_candidates";
            }
        }
        if (plan.timeBudgetMs != null && resolveRerankTimeoutMs(plan) <= 0) {
            return "rerank_budget_exhausted";
        }
        return null;
    }

    private RerankOutcome applyRerank(
        ExecutionPlan plan,
        RetrievalResult retrieval,
        int from,
        int size,
        String traceId,
        String requestId,
        String traceparent
    ) {
        String skipReason = shouldSkipRerank(plan, retrieval);
        if (skipReason != null) {
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                false,
                false,
                0L,
                null,
                skipReason
            );
        }

        CircuitBreaker rerankBreaker = resilienceRegistry.getRerankBreaker();
        if (!rerankBreaker.allowRequest()) {
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                false,
                0L,
                "rerank_circuit_open",
                null
            );
        }

        int limit = Math.min(plan.rerankTopK, retrieval.fused.size());
        List<RrfFusion.Candidate> rerankSlice = retrieval.fused.subList(0, limit);
        List<RerankRequest.Candidate> rerankCandidates = buildRerankCandidates(rerankSlice, retrieval.sources);
        Map<String, RrfFusion.Candidate> fusedById = toCandidateMap(retrieval.fused);

        int timeoutMs = resolveRerankTimeoutMs(plan);
        boolean rerankDebug = plan.debugEnabled || plan.explainEnabled;

        CompletableFuture<RerankResponse> future = CompletableFuture.supplyAsync(
            () -> rankingGateway.rerank(
                plan.queryText,
                rerankCandidates,
                limit,
                timeoutMs,
                rerankDebug,
                traceId,
                requestId,
                traceparent
            ),
            searchExecutor
        );

        long started = System.nanoTime();
        int hedgeDelayMs = Math.max(0, resilienceRegistry.getProperties().getRerankHedgeDelayMs());

        try {
            RerankResponse rerankResponse;
            if (hedgeDelayMs > 0 && timeoutMs > 0 && hedgeDelayMs < timeoutMs) {
                rerankResponse = future.get(hedgeDelayMs, TimeUnit.MILLISECONDS);
            } else if (timeoutMs > 0) {
                rerankResponse = future.get(timeoutMs, TimeUnit.MILLISECONDS);
            } else {
                rerankResponse = future.get();
            }

            long tookMs = (System.nanoTime() - started) / 1_000_000L;
            if (rerankResponse != null && rerankResponse.getHits() != null) {
                rerankBreaker.recordSuccess();
                return new RerankOutcome(
                    buildHitsFromRanking(rerankResponse.getHits(), fusedById, from, size, retrieval.sources),
                    true,
                    false,
                    false,
                    tookMs,
                    null,
                    null
                );
            }
            rerankBreaker.recordFailure();
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                false,
                tookMs,
                "rerank_empty",
                null
            );
        } catch (TimeoutException e) {
            future.cancel(true);
            rerankBreaker.recordFailure();
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                true,
                0L,
                "rerank_timeout",
                null
            );
        } catch (ExecutionException e) {
            rerankBreaker.recordFailure();
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                false,
                0L,
                errorMessage(e),
                null
            );
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            rerankBreaker.recordFailure();
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                false,
                0L,
                "rerank_interrupted",
                null
            );
        } catch (RankingUnavailableException e) {
            rerankBreaker.recordFailure();
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                false,
                0L,
                e.getMessage(),
                null
            );
        }
    }

    private SearchResponse buildResponse(
        long started,
        String traceId,
        String requestId,
        List<BookHit> hits,
        int total,
        boolean rankingApplied,
        String strategy,
        SearchResponse.Debug debug
    ) {
        long tookMs = (System.nanoTime() - started) / 1_000_000L;
        SearchResponse response = new SearchResponse();
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs(tookMs);
        response.setRankingApplied(rankingApplied);
        response.setStrategy(strategy);
        response.setTotal(Math.max(total, hits == null ? 0 : hits.size()));
        response.setHits(hits);
        response.setDebug(debug);
        return response;
    }

    private void assignExperimentBucket(ExecutionPlan plan, String requestId) {
        plan.experimentBucket = "control";
        if (experimentProperties == null || !experimentProperties.isEnabled()) {
            return;
        }
        if (shouldSkipExplore(plan)) {
            return;
        }
        double rollout = experimentProperties.getExploreRate();
        if (rollout <= 0.0) {
            return;
        }
        String seedSource = requestId == null ? plan.queryText : requestId;
        double value = hashToUnitInterval(seedSource);
        if (value < rollout) {
            plan.experimentBucket = "explore";
        }
    }

    private List<BookHit> maybeApplyExploration(
        ExecutionPlan plan,
        List<BookHit> hits,
        int from,
        int size,
        String requestId,
        SearchResponse.Debug debug
    ) {
        if (hits == null || hits.isEmpty()) {
            return hits;
        }
        if (!"explore".equals(plan.experimentBucket)) {
            return hits;
        }
        if (from > 0) {
            return hits;
        }
        if (hits.size() < experimentProperties.getMinResults()) {
            return hits;
        }
        int start = Math.max(0, experimentProperties.getShuffleStart() - 1);
        int end = Math.min(hits.size(), experimentProperties.getShuffleEnd());
        if (end - start < 2) {
            return hits;
        }

        List<BookHit> reordered = new ArrayList<>(hits);
        List<BookHit> slice = new ArrayList<>(reordered.subList(start, end));
        long seed = seedFrom(requestId, plan.queryText);
        Collections.shuffle(slice, new Random(seed));
        for (int i = 0; i < slice.size(); i++) {
            reordered.set(start + i, slice.get(i));
        }
        for (int i = 0; i < reordered.size(); i++) {
            BookHit hit = reordered.get(i);
            if (hit != null) {
                hit.setRank(i + 1);
            }
        }
        plan.exploreApplied = true;
        if (debug != null) {
            debug.setExperimentBucket(plan.experimentBucket);
            debug.setExperimentApplied(true);
        }
        return reordered;
    }

    private boolean shouldSkipExplore(ExecutionPlan plan) {
        String query = plan.queryText;
        if (query == null) {
            return true;
        }
        String trimmed = query.trim();
        if (trimmed.length() < experimentProperties.getMinQueryLength()) {
            return true;
        }
        if (experimentProperties.isExcludeQuoted() && (trimmed.contains("\"") || trimmed.contains("'"))) {
            return true;
        }
        if (experimentProperties.isExcludeIsbn() && isIsbnQuery(trimmed)) {
            return true;
        }
        return false;
    }

    private boolean isIsbnQuery(String query) {
        if (query == null) {
            return false;
        }
        String normalized = query.replaceAll("[^0-9Xx]", "");
        if (normalized.length() != 10 && normalized.length() != 13) {
            return false;
        }
        return ISBN_PATTERN.matcher(normalized).matches();
    }

    private double hashToUnitInterval(String value) {
        if (value == null || value.isEmpty()) {
            return 1.0;
        }
        int hash = value.hashCode();
        long unsigned = Integer.toUnsignedLong(hash);
        return unsigned / (double) 0x1_0000_0000L;
    }

    private long seedFrom(String requestId, String queryText) {
        String seedSource = requestId == null || requestId.isBlank() ? queryText : requestId;
        return seedSource == null ? 0L : seedSource.hashCode();
    }

    private ExecutionPlan buildLegacyPlan(SearchRequest request, Options options) {
        ExecutionPlan plan = new ExecutionPlan((QueryContextV1_1) null);
        QueryContext queryContext = request.getQueryContext();
        QueryContext.RetrievalHints retrievalHints = queryContext == null ? null : queryContext.getRetrievalHints();

        plan.queryText = resolveLegacyQueryText(request, queryContext);
        plan.queryTextSourceUsed = "legacy";
        plan.lexicalEnabled = true;
        plan.rerankEnabled = true;

        boolean enableVector = options.getEnableVector() == null || options.getEnableVector();
        boolean allowVector = applyStrategy(enableVector, retrievalHints == null ? null : retrievalHints.getStrategy());
        plan.vectorEnabled = allowVector;

        int topK = DEFAULT_LEX_TOP_K;
        int vecTopK = DEFAULT_VEC_TOP_K;
        if (retrievalHints != null && retrievalHints.getTopK() != null) {
            topK = clamp(retrievalHints.getTopK(), MIN_TOP_K, MAX_TOP_K);
            vecTopK = topK;
        }
        plan.lexicalTopK = topK;
        plan.vectorTopK = vecTopK;
        plan.rrfK = options.getRrfK() != null ? options.getRrfK() : DEFAULT_RRF_K;
        plan.rerankTopK = Math.min(DEFAULT_LEX_TOP_K, Math.max(DEFAULT_SIZE, topK));
        applyRerankTopKGuardrail(plan);
        plan.boost = retrievalHints == null ? null : retrievalHints.getBoost();
        plan.filters = Collections.emptyList();
        plan.fallbackPolicy = Collections.emptyList();

        Integer timeBudgetMs = null;
        if (options.getTimeoutMs() != null) {
            timeBudgetMs = clamp(options.getTimeoutMs(), MIN_TIME_BUDGET_MS, MAX_TIME_BUDGET_MS);
        } else if (retrievalHints != null && retrievalHints.getTimeBudgetMs() != null) {
            timeBudgetMs = clamp(retrievalHints.getTimeBudgetMs(), MIN_TIME_BUDGET_MS, MAX_TIME_BUDGET_MS);
        }
        plan.timeBudgetMs = timeBudgetMs;
        plan.lexicalBudgetMs = null;
        plan.vectorBudgetMs = null;
        plan.rerankBudgetMs = null;
        applyBudgetSplit(plan);

        plan.debugEnabled = Boolean.TRUE.equals(options.getDebug());
        plan.explainEnabled = Boolean.TRUE.equals(options.getExplain());
        return plan;
    }

    private void applyRerankTopKGuardrail(ExecutionPlan plan) {
        if (plan == null || rerankPolicy == null) {
            return;
        }
        int maxTopK = rerankPolicy.getMaxTopK();
        if (maxTopK > 0 && plan.rerankTopK > maxTopK) {
            plan.rerankTopK = maxTopK;
        }
    }

    private void applyBudgetSplit(ExecutionPlan plan) {
        if (plan == null || plan.timeBudgetMs == null) {
            return;
        }
        int total = plan.timeBudgetMs;
        if (budgetProperties == null || !budgetProperties.isEnabled()) {
            if (plan.lexicalBudgetMs == null) {
                plan.lexicalBudgetMs = total;
            }
            if (plan.vectorBudgetMs == null) {
                plan.vectorBudgetMs = total;
            }
            if (plan.rerankBudgetMs == null) {
                plan.rerankBudgetMs = total;
            }
            return;
        }

        double lexShare = Math.max(0.0, budgetProperties.getLexicalShare());
        double vecShare = Math.max(0.0, budgetProperties.getVectorShare());
        double rerankShare = Math.max(0.0, budgetProperties.getRerankShare());
        double sum = lexShare + vecShare + rerankShare;
        if (sum <= 0.0) {
            return;
        }
        lexShare /= sum;
        vecShare /= sum;
        rerankShare /= sum;

        int minStageMs = Math.max(0, budgetProperties.getMinStageMs());
        if (plan.lexicalBudgetMs == null) {
            plan.lexicalBudgetMs = clampBudget(Math.round(total * (float) lexShare), minStageMs, total);
        }
        if (plan.vectorBudgetMs == null) {
            plan.vectorBudgetMs = plan.vectorEnabled
                ? clampBudget(Math.round(total * (float) vecShare), minStageMs, total)
                : 0;
        }
        if (plan.rerankBudgetMs == null) {
            plan.rerankBudgetMs = plan.rerankEnabled
                ? clampBudget(Math.round(total * (float) rerankShare), minStageMs, total)
                : 0;
        }
    }

    private int clampBudget(int value, int min, int max) {
        int lower = Math.max(0, min);
        int upper = Math.max(lower, max);
        return Math.min(Math.max(value, lower), upper);
    }

    private SearchResponse.Debug buildDebug(
        ExecutionPlan plan,
        RetrievalResult retrieval,
        RerankOutcome rerankOutcome,
        String appliedFallbackId,
        String cacheKey,
        boolean cacheHit,
        EnhanceOutcome enhanceOutcome
    ) {
        boolean include = plan.debugEnabled
            || plan.explainEnabled
            || appliedFallbackId != null
            || cacheHit
            || (enhanceOutcome != null && enhanceOutcome.attempted);
        if (!include) {
            return null;
        }

        SearchResponse.Debug debug = new SearchResponse.Debug();
        debug.setAppliedFallbackId(appliedFallbackId);
        debug.setQueryTextSourceUsed(plan.queryTextSourceUsed);

        SearchResponse.Stages stages = new SearchResponse.Stages();
        stages.setLexical(plan.lexicalEnabled);
        stages.setVector(plan.vectorEnabled);
        stages.setRerank(plan.rerankEnabled);
        debug.setStages(stages);

        if (plan.debugEnabled || plan.explainEnabled) {
            Map<String, Object> queryDsl = new HashMap<>();
            if (retrieval.lexical.getQueryDsl() != null) {
                queryDsl.put("lexical", retrieval.lexical.getQueryDsl());
            }
            if (retrieval.vector.getQueryDsl() != null) {
                queryDsl.put("vector", retrieval.vector.getQueryDsl());
            }
            if (!queryDsl.isEmpty()) {
                debug.setQueryDsl(queryDsl);
            }

            SearchResponse.Retrieval retrievalDebug = new SearchResponse.Retrieval();
            retrievalDebug.setLexical(buildStage(retrieval.lexical, plan.lexicalTopK, null));
            retrievalDebug.setVector(buildStage(retrieval.vector, plan.vectorTopK, vectorRetriever.mode()));
            retrievalDebug.setFusion(buildFusionStage(retrieval));
            retrievalDebug.setRerank(buildRerankStage(plan, rerankOutcome));
            debug.setRetrieval(retrievalDebug);
        }

        SearchResponse.Cache cache = new SearchResponse.Cache();
        cache.setHit(cacheHit);
        cache.setKey(cacheKey);
        debug.setCache(cache);

        List<String> warnings = buildWarnings(retrieval, rerankOutcome);
        if (!warnings.isEmpty()) {
            debug.setWarnings(warnings);
        }
        if (enhanceOutcome != null && enhanceOutcome.attempted) {
            debug.setEnhanceApplied(enhanceOutcome.applied);
            debug.setEnhanceReason(enhanceOutcome.reason);
            debug.setEnhanceStrategy(enhanceOutcome.strategy);
            debug.setEnhanceFinalQuery(enhanceOutcome.finalQuery);
            debug.setEnhanceFinalSource(enhanceOutcome.finalSource);
            debug.setEnhanceImproved(enhanceOutcome.improved);
            debug.setEnhanceSkipReason(enhanceOutcome.skipReason);
        }
        debug.setExperimentBucket(plan.experimentBucket);
        debug.setExperimentApplied(plan.exploreApplied);

        return debug;
    }

    private SearchResponse.Stage buildStage(RetrievalStageResult result, int topK, String mode) {
        SearchResponse.Stage stage = new SearchResponse.Stage();
        if (result != null) {
            stage.setTookMs(result.getTookMs());
            stage.setDocCount(result.getDocIds() == null ? 0 : result.getDocIds().size());
            stage.setError(result.isError());
            stage.setTimedOut(result.isTimedOut());
            stage.setErrorMessage(result.getErrorMessage());
        }
        stage.setTopK(topK);
        stage.setMode(mode);
        return stage;
    }

    private SearchResponse.Stage buildFusionStage(RetrievalResult retrieval) {
        SearchResponse.Stage stage = new SearchResponse.Stage();
        stage.setDocCount(retrieval.fused == null ? 0 : retrieval.fused.size());
        stage.setTookMs(retrieval.fusionTookMs);
        return stage;
    }

    private SearchResponse.Stage buildRerankStage(ExecutionPlan plan, RerankOutcome rerankOutcome) {
        SearchResponse.Stage stage = new SearchResponse.Stage();
        stage.setTopK(plan.rerankTopK);
        stage.setTookMs(rerankOutcome.tookMs);
        stage.setError(rerankOutcome.rerankError);
        stage.setTimedOut(rerankOutcome.rerankTimedOut);
        stage.setErrorMessage(rerankOutcome.skipReason != null ? rerankOutcome.skipReason : rerankOutcome.errorMessage);
        return stage;
    }

    private List<String> buildWarnings(RetrievalResult retrieval, RerankOutcome rerankOutcome) {
        List<String> warnings = new ArrayList<>();
        if (retrieval.lexical.isError()) {
            warnings.add("lexical_error");
        }
        if (retrieval.lexical.isTimedOut()) {
            warnings.add("lexical_timeout");
        }
        if (retrieval.vector.isSkipped()) {
            String reason = retrieval.vector.getErrorMessage();
            if (reason != null && reason.contains("vector_disabled")) {
                // no warning for intentionally disabled vector retrieval
            } else if (reason != null && !reason.isBlank()) {
                warnings.add(reason);
            } else {
                warnings.add("vector_skipped");
            }
        }
        if (retrieval.vector.isError() && !retrieval.vector.isSkipped()) {
            String reason = retrieval.vector.getErrorMessage();
            if (reason != null && !reason.isBlank()) {
                warnings.add(reason);
            } else {
                warnings.add("vector_error");
            }
        }
        if (retrieval.vector.isTimedOut()) {
            warnings.add("vector_timeout");
        }
        if (rerankOutcome.rerankTimedOut) {
            warnings.add("rerank_timeout");
        }
        if (rerankOutcome.rerankError) {
            warnings.add("rerank_error");
        }
        if (rerankOutcome.skipReason != null && !rerankOutcome.skipReason.isBlank()) {
            warnings.add(rerankOutcome.skipReason);
        }
        return warnings;
    }

    private String buildSerpCacheKey(ExecutionPlan plan, int from, int size) {
        if (!serpCacheService.isEnabled()) {
            return null;
        }
        Map<String, Object> fields = serpCacheService.baseKeyFields(
            plan.queryText,
            plan.lexicalEnabled,
            plan.vectorEnabled,
            plan.lexicalTopK,
            plan.vectorTopK,
            plan.rrfK,
            plan.rerankEnabled,
            plan.rerankTopK,
            from,
            size,
            plan.boost,
            plan.lexicalOperator,
            plan.minimumShouldMatch,
            plan.filters,
            plan.lexicalFields
        );
        if (plan.experimentBucket != null) {
            fields.put("experiment_bucket", plan.experimentBucket);
        }
        if (plan.lexicalQueryOverride != null && !plan.lexicalQueryOverride.isEmpty()) {
            fields.put("lexical_query_override", plan.lexicalQueryOverride);
        }
        return serpCacheService.buildKey(fields);
    }

    private Optional<SearchResponse> maybeServeSerpCache(
        String cacheKey,
        String traceId,
        String requestId,
        long started,
        ExecutionPlan plan
    ) {
        return maybeServeSerpCache(cacheKey, traceId, requestId, started, plan, false);
    }

    private Optional<SearchResponse> maybeServeSerpCache(
        String cacheKey,
        String traceId,
        String requestId,
        long started,
        ExecutionPlan plan,
        boolean degradedOnly
    ) {
        if (!serpCacheService.isEnabled() || cacheKey == null) {
            return Optional.empty();
        }
        if (!degradedOnly && (plan.debugEnabled || plan.explainEnabled)) {
            return Optional.empty();
        }
        Optional<SerpCacheService.CachedResponse> cached = serpCacheService.get(cacheKey);
        if (cached.isEmpty()) {
            return Optional.empty();
        }
        SerpCacheService.CachedResponse entry = cached.get();
        SearchResponse cachedResponse = copySearchResponse(entry.getResponse(), traceId, requestId, started);
        SearchResponse.Debug debug = buildDebug(
            plan,
            emptyRetrieval(plan),
            emptyRerankOutcome(),
            null,
            cacheKey,
            true,
            EnhanceOutcome.notAttempted()
        );
        if (debug != null && debug.getCache() != null) {
            long ageMs = Math.max(0L, System.currentTimeMillis() - entry.getCreatedAt());
            long ttlMs = Math.max(0L, entry.getExpiresAt() - entry.getCreatedAt());
            debug.getCache().setAgeMs(ageMs);
            debug.getCache().setTtlMs(ttlMs);
        }
        cachedResponse.setDebug(debug);
        return Optional.of(cachedResponse);
    }

    private boolean shouldStoreSerpCache(ExecutionPlan plan, SearchResponse response, String cacheKey) {
        if (!serpCacheService.isEnabled() || cacheKey == null) {
            return false;
        }
        if (plan.debugEnabled || plan.explainEnabled) {
            return false;
        }
        return response != null && response.getHits() != null && !response.getHits().isEmpty();
    }

    private SearchResponse stripDebug(SearchResponse response) {
        if (response == null) {
            return null;
        }
        SearchResponse stripped = new SearchResponse();
        stripped.setTraceId(response.getTraceId());
        stripped.setRequestId(response.getRequestId());
        stripped.setTookMs(response.getTookMs());
        stripped.setRankingApplied(response.isRankingApplied());
        stripped.setStrategy(response.getStrategy());
        stripped.setTotal(response.getTotal());
        stripped.setHits(response.getHits());
        stripped.setExperimentBucket(response.getExperimentBucket());
        stripped.setDebug(null);
        return stripped;
    }

    private SearchResponse copySearchResponse(SearchResponse response, String traceId, String requestId, long started) {
        SearchResponse copied = new SearchResponse();
        copied.setTraceId(traceId);
        copied.setRequestId(requestId);
        copied.setTookMs((System.nanoTime() - started) / 1_000_000L);
        if (response != null) {
            copied.setRankingApplied(response.isRankingApplied());
            copied.setStrategy(response.getStrategy());
            copied.setTotal(response.getTotal());
            copied.setHits(response.getHits());
            copied.setExperimentBucket(response.getExperimentBucket());
        }
        return copied;
    }

    private RetrievalResult emptyRetrieval(ExecutionPlan plan) {
        RetrievalStageResult emptyStage = RetrievalStageResult.empty();
        return new RetrievalResult(List.of(), Collections.emptyMap(), emptyStage, emptyStage, 0L);
    }

    private RerankOutcome emptyRerankOutcome() {
        return new RerankOutcome(List.of(), false, false, false, 0L, null, null);
    }

    private int resolveRerankTimeoutMs(ExecutionPlan plan) {
        if (plan == null) {
            return 0;
        }
        if (plan.rerankBudgetMs != null) {
            return plan.rerankBudgetMs;
        }
        if (plan.timeBudgetMs != null) {
            return plan.timeBudgetMs;
        }
        return 0;
    }

    private RetrievalStageResult awaitStage(CompletableFuture<RetrievalStageResult> future, Integer timeoutMs) {
        try {
            if (timeoutMs != null && timeoutMs > 0) {
                return future.get(timeoutMs, TimeUnit.MILLISECONDS);
            }
            return future.get();
        } catch (TimeoutException e) {
            future.cancel(true);
            return RetrievalStageResult.timedOut();
        } catch (ExecutionException e) {
            return RetrievalStageResult.error(errorMessage(e));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return RetrievalStageResult.error("interrupted");
        }
    }

    private String errorMessage(Exception e) {
        if (e == null) {
            return null;
        }
        Throwable cause = e instanceof ExecutionException ? e.getCause() : e;
        if (cause == null) {
            return e.getMessage();
        }
        return cause.getMessage();
    }

    private BookDetailResponse copyBookDetailResponse(
        BookDetailResponse response,
        String traceId,
        String requestId,
        long tookMs
    ) {
        if (response == null) {
            return null;
        }
        BookDetailResponse copied = new BookDetailResponse();
        copied.setDocId(response.getDocId());
        copied.setSource(response.getSource());
        copied.setTraceId(traceId);
        copied.setRequestId(requestId);
        copied.setTookMs(tookMs);
        return copied;
    }

    private ExecutionPlan buildPlanFromQcV11(QueryContextV1_1 qc, Options options) {
        ExecutionPlan plan = new ExecutionPlan(qc);
        QueryContextV1_1.RetrievalHints hints = qc.getRetrievalHints();
        QueryContextV1_1.Query query = qc.getQuery();

        QueryTextSelection selection = selectQueryText(query, hints == null ? null : hints.getQueryTextSource());
        plan.queryText = selection.text;
        plan.queryTextSourceUsed = selection.sourceUsed;
        if (isBlank(plan.queryText)
            && qc.getUnderstanding() != null
            && qc.getUnderstanding().getConstraints() != null) {
            plan.queryText = trimToNull(qc.getUnderstanding().getConstraints().getResidualText());
            if (!isBlank(plan.queryText)) {
                plan.queryTextSourceUsed = "understanding.residualText";
            }
        }

        QueryContextV1_1.Lexical lexical = hints == null ? null : hints.getLexical();
        plan.lexicalEnabled = lexical == null || lexical.getEnabled() == null || lexical.getEnabled();
        plan.lexicalTopK = lexical != null && lexical.getTopKHint() != null
            ? clamp(lexical.getTopKHint(), QC_LEX_TOP_K_MIN, QC_LEX_TOP_K_MAX)
            : DEFAULT_QC_LEX_TOP_K;
        plan.lexicalOperator = normalizeOperator(lexical == null ? null : lexical.getOperator());
        plan.minimumShouldMatch = blankToNull(lexical == null ? null : lexical.getMinimumShouldMatch());
        plan.lexicalFields = mapPreferredFields(lexical == null ? null : lexical.getPreferredLogicalFields());
        plan.lexicalQueryOverride = buildLexicalQueryOverride(qc, plan.queryText);

        QueryContextV1_1.Vector vector = hints == null ? null : hints.getVector();
        plan.vectorEnabled = vector == null || vector.getEnabled() == null || vector.getEnabled();
        plan.vectorTopK = vector != null && vector.getTopKHint() != null
            ? clamp(vector.getTopKHint(), QC_VEC_TOP_K_MIN, QC_VEC_TOP_K_MAX)
            : DEFAULT_QC_VEC_TOP_K;
        plan.rrfK = DEFAULT_RRF_K;
        if (vector != null && vector.getFusionHint() != null && vector.getFusionHint().getK() != null) {
            plan.rrfK = clamp(vector.getFusionHint().getK(), QC_RRF_K_MIN, QC_RRF_K_MAX);
        }
        if (vector != null && vector.getFusionHint() != null) {
            plan.fusionMethod = FusionMethod.fromString(vector.getFusionHint().getMethod());
        }

        QueryContextV1_1.Rerank rerank = hints == null ? null : hints.getRerank();
        plan.rerankEnabled = rerank != null && Boolean.TRUE.equals(rerank.getEnabled());
        plan.rerankTopK = rerank != null && rerank.getTopKHint() != null
            ? clamp(rerank.getTopKHint(), QC_RERANK_TOP_K_MIN, QC_RERANK_TOP_K_MAX)
            : DEFAULT_QC_RERANK_TOP_K;
        applyRerankTopKGuardrail(plan);

        plan.filters = buildFilters(hints);
        plan.fallbackPolicy = hints == null || hints.getFallbackPolicy() == null
            ? Collections.emptyList()
            : hints.getFallbackPolicy();

        int timeoutMs = DEFAULT_QC_TIMEOUT_MS;
        if (options != null && options.getTimeoutMs() != null) {
            timeoutMs = clamp(options.getTimeoutMs(), QC_TIMEOUT_MIN_MS, QC_TIMEOUT_MAX_MS);
        } else if (hints != null && hints.getExecutionHint() != null && hints.getExecutionHint().getTimeoutMs() != null) {
            timeoutMs = clamp(hints.getExecutionHint().getTimeoutMs(), QC_TIMEOUT_MIN_MS, QC_TIMEOUT_MAX_MS);
        }
        plan.timeBudgetMs = timeoutMs;

        if (hints != null && hints.getExecutionHint() != null && hints.getExecutionHint().getBudgetMs() != null) {
            QueryContextV1_1.BudgetMs budget = hints.getExecutionHint().getBudgetMs();
            if (budget.getLexical() != null) {
                plan.lexicalBudgetMs = clamp(budget.getLexical(), QC_TIMEOUT_MIN_MS, QC_TIMEOUT_MAX_MS);
            }
            if (budget.getVector() != null) {
                plan.vectorBudgetMs = clamp(budget.getVector(), QC_TIMEOUT_MIN_MS, QC_TIMEOUT_MAX_MS);
            }
            if (budget.getRerank() != null) {
                plan.rerankBudgetMs = clamp(budget.getRerank(), QC_TIMEOUT_MIN_MS, QC_TIMEOUT_MAX_MS);
            }
        }
        applyBudgetSplit(plan);

        plan.debugEnabled = options != null && Boolean.TRUE.equals(options.getDebug());
        plan.explainEnabled = options != null && Boolean.TRUE.equals(options.getExplain());

        return plan;
    }

    private QueryTextSelection selectQueryText(QueryContextV1_1.Query query, String sourceHint) {
        if (query == null) {
            return new QueryTextSelection(null, null);
        }

        String normalized = sourceHint == null ? null : sourceHint.trim().toLowerCase(Locale.ROOT);
        if ("query.final".equals(normalized)) {
            return new QueryTextSelection(trimToNull(query.getFinalValue()), "query.final");
        }
        if ("query.norm".equals(normalized)) {
            return new QueryTextSelection(trimToNull(query.getNorm()), "query.norm");
        }
        if ("query.raw".equals(normalized)) {
            return new QueryTextSelection(trimToNull(query.getRaw()), "query.raw");
        }

        if (!isBlank(query.getFinalValue())) {
            return new QueryTextSelection(trimToNull(query.getFinalValue()), "query.final");
        }
        if (!isBlank(query.getNorm())) {
            return new QueryTextSelection(trimToNull(query.getNorm()), "query.norm");
        }
        if (!isBlank(query.getRaw())) {
            return new QueryTextSelection(trimToNull(query.getRaw()), "query.raw");
        }
        return new QueryTextSelection(null, null);
    }

    private String resolveLegacyQueryText(SearchRequest request, QueryContext queryContext) {
        if (queryContext != null && queryContext.getQuery() != null) {
            String candidate = firstNonBlank(
                queryContext.getQuery().getCanonical(),
                queryContext.getQuery().getNormalized(),
                queryContext.getQuery().getRaw()
            );
            return candidate == null ? null : candidate.trim();
        }
        if (request.getQuery() != null && request.getQuery().getRaw() != null) {
            return request.getQuery().getRaw().trim();
        }
        return null;
    }

    private List<String> mapPreferredFields(List<String> logicalFields) {
        if (logicalFields == null || logicalFields.isEmpty()) {
            return null;
        }
        List<String> mapped = new ArrayList<>();
        for (String field : logicalFields) {
            if (field == null) {
                continue;
            }
            String normalized = field.trim().toLowerCase(Locale.ROOT);
            if ("title_ko".equals(normalized)) {
                addIfAbsent(mapped, "title_ko");
                addIfAbsent(mapped, "title_ko.reading");
                addIfAbsent(mapped, "title_ko.compact");
                addIfAbsent(mapped, "title_ko.auto");
            } else if ("title_en".equals(normalized)) {
                addIfAbsent(mapped, "title_en");
                addIfAbsent(mapped, "title_en.compact");
                addIfAbsent(mapped, "title_en.auto");
            } else if ("author_ko".equals(normalized)) {
                addIfAbsent(mapped, "author_names_ko");
                addIfAbsent(mapped, "author_names_ko.reading");
                addIfAbsent(mapped, "author_names_ko.compact");
                addIfAbsent(mapped, "author_names_ko.auto");
                addIfAbsent(mapped, "author_names_en");
                addIfAbsent(mapped, "author_names_en.compact");
                addIfAbsent(mapped, "author_names_en.auto");
            } else if ("series_ko".equals(normalized) || "series_name".equals(normalized)) {
                addIfAbsent(mapped, "series_name");
                addIfAbsent(mapped, "series_name.compact");
                addIfAbsent(mapped, "series_name.auto");
            } else if ("publisher".equals(normalized) || "publisher_name".equals(normalized)) {
                addIfAbsent(mapped, "publisher_name");
                addIfAbsent(mapped, "publisher_name.compact");
                addIfAbsent(mapped, "publisher_name.auto");
            } else if ("isbn13".equals(normalized) || "isbn".equals(normalized)) {
                addIfAbsent(mapped, "identifiers.isbn13");
            }
        }
        return mapped.isEmpty() ? null : mapped;
    }

    private void addIfAbsent(List<String> target, String value) {
        if (!target.contains(value)) {
            target.add(value);
        }
    }

    private Map<String, Object> buildLexicalQueryOverride(QueryContextV1_1 qc, String selectedQueryText) {
        if (qc == null || qc.getUnderstanding() == null || qc.getUnderstanding().getEntities() == null) {
            return null;
        }
        QueryContextV1_1.Entities entities = qc.getUnderstanding().getEntities();
        String residualText = qc.getUnderstanding().getConstraints() == null
            ? null
            : trimToNull(qc.getUnderstanding().getConstraints().getResidualText());
        String fallbackText = firstNonBlank(residualText, selectedQueryText);

        List<String> isbnValues = normalizeIsbnValues(cleanValues(entities.getIsbn()));
        if (!isbnValues.isEmpty()) {
            List<Map<String, Object>> isbnShould = new ArrayList<>();
            for (String isbn : isbnValues) {
                isbnShould.add(Map.of("term", Map.of("identifiers.isbn13", isbn)));
                isbnShould.add(Map.of("term", Map.of("identifiers.isbn10", isbn)));
            }

            Map<String, Object> isbnBool = new LinkedHashMap<>();
            isbnBool.put("should", isbnShould);
            isbnBool.put("minimum_should_match", 1);

            Map<String, Object> bool = new LinkedHashMap<>();
            bool.put("must", List.of(Map.of("bool", isbnBool)));
            if (!isBlank(fallbackText)) {
                bool.put("should", List.of(buildIsbnResidualDisMax(fallbackText)));
            }
            bool.put("minimum_should_match", 0);
            return Map.of("bool", bool);
        }

        List<Map<String, Object>> must = new ArrayList<>();
        String author = firstValue(entities.getAuthor());
        String title = firstValue(entities.getTitle());
        String series = firstValue(entities.getSeries());
        String publisher = firstValue(entities.getPublisher());
        if (!isBlank(author)) {
            must.add(buildAuthorEntityMustBlock(author));
        }
        if (!isBlank(title)) {
            must.add(buildTitleEntityMustBlock(title));
        }
        if (!isBlank(series)) {
            must.add(buildSeriesEntityMustBlock(series));
        }
        if (!isBlank(publisher)) {
            must.add(buildPublisherEntityMustBlock(publisher));
        }

        if (must.isEmpty()) {
            return null;
        }

        Map<String, Object> bool = new LinkedHashMap<>();
        bool.put("must", must);
        if (!isBlank(fallbackText)) {
            bool.put("should", List.of(buildResidualMultiMatch(fallbackText)));
        }
        bool.put("minimum_should_match", 0);
        return Map.of("bool", bool);
    }

    private Map<String, Object> buildAuthorEntityMustBlock(String author) {
        return Map.of(
            "bool",
            Map.of(
                "should",
                List.of(
                    Map.of("match", Map.of("author_names_ko", Map.of("query", author, "boost", 3.0d))),
                    Map.of("match", Map.of("author_names_ko.reading", Map.of("query", author, "boost", 0.9d))),
                    Map.of("match", Map.of("author_names_ko.compact", Map.of("query", author, "boost", 2.2d))),
                    Map.of("match", Map.of("author_names_en", Map.of("query", author, "boost", 1.8d))),
                    buildMultiMatchClause(
                        author,
                        "bool_prefix",
                        List.of("author_names_ko.auto^1.6", "author_names_en.auto^1.3"),
                        null
                    )
                ),
                "minimum_should_match",
                1
            )
        );
    }

    private Map<String, Object> buildTitleEntityMustBlock(String title) {
        return Map.of(
            "bool",
            Map.of(
                "should",
                List.of(
                    Map.of("match", Map.of("title_ko", Map.of("query", title, "boost", 3.0d))),
                    Map.of("match", Map.of("title_ko.reading", Map.of("query", title, "boost", 1.2d))),
                    Map.of("match", Map.of("title_ko.compact", Map.of("query", title, "boost", 2.2d))),
                    Map.of("match_phrase", Map.of("title_ko", Map.of("query", title, "slop", 1, "boost", 6.0d))),
                    buildMultiMatchClause(
                        title,
                        "bool_prefix",
                        List.of("title_ko.auto^1.8", "title_en.auto^1.5"),
                        null
                    )
                ),
                "minimum_should_match",
                1
            )
        );
    }

    private Map<String, Object> buildSeriesEntityMustBlock(String series) {
        return Map.of(
            "bool",
            Map.of(
                "should",
                List.of(
                    Map.of("match", Map.of("series_name", Map.of("query", series, "boost", 2.5d))),
                    Map.of("match", Map.of("series_name.compact", Map.of("query", series, "boost", 1.9d))),
                    Map.of("match_phrase", Map.of("series_name", Map.of("query", series, "slop", 1, "boost", 4.0d))),
                    buildMultiMatchClause(
                        series,
                        "bool_prefix",
                        List.of("series_name.auto^1.6"),
                        null
                    )
                ),
                "minimum_should_match",
                1
            )
        );
    }

    private Map<String, Object> buildPublisherEntityMustBlock(String publisher) {
        return Map.of(
            "bool",
            Map.of(
                "should",
                List.of(
                    Map.of("match", Map.of("publisher_name", Map.of("query", publisher, "boost", 2.0d))),
                    Map.of("match", Map.of("publisher_name.compact", Map.of("query", publisher, "boost", 1.5d))),
                    buildMultiMatchClause(
                        publisher,
                        "bool_prefix",
                        List.of("publisher_name.auto^1.4"),
                        null
                    )
                ),
                "minimum_should_match",
                1
            )
        );
    }

    private Map<String, Object> buildIsbnResidualDisMax(String residual) {
        return Map.of(
            "dis_max",
            Map.of(
                "tie_breaker",
                0.2d,
                "queries",
                List.of(
                    buildMultiMatchClause(
                        residual,
                        "best_fields",
                        List.of(
                            "title_ko^3",
                            "title_en^2.5",
                            "series_name^2",
                            "publisher_name^1.8",
                            "author_names_ko^1.6",
                            "author_names_en^1.4"
                        ),
                        "or"
                    ),
                    buildMultiMatchClause(
                        residual,
                        "best_fields",
                        List.of("title_ko.reading^0.9", "author_names_ko.reading^0.5"),
                        "or"
                    ),
                    buildMultiMatchClause(
                        residual,
                        "best_fields",
                        List.of(
                            "title_ko.compact^2.2",
                            "title_en.compact^2.0",
                            "series_name.compact^1.6",
                            "publisher_name.compact^1.4",
                            "author_names_ko.compact^1.4"
                        ),
                        "or"
                    ),
                    buildMultiMatchClause(
                        residual,
                        "bool_prefix",
                        List.of(
                            "title_ko.auto^1.8",
                            "title_en.auto^1.6",
                            "series_name.auto^1.3",
                            "publisher_name.auto^1.2",
                            "author_names_ko.auto^1.2"
                        ),
                        null
                    )
                )
            )
        );
    }

    private Map<String, Object> buildResidualMultiMatch(String query) {
        return buildMultiMatchClause(
            query,
            "best_fields",
            List.of(
                "title_ko^2",
                "title_ko.reading^0.8",
                "title_en^1.6",
                "series_name^1.4",
                "publisher_name^1.2",
                "author_names_ko^1.2",
                "author_names_ko.reading^0.5",
                "author_names_en^1.1"
            ),
            "or"
        );
    }

    private Map<String, Object> buildMultiMatchClause(
        String query,
        String type,
        List<String> fields,
        String operator
    ) {
        Map<String, Object> multiMatch = new LinkedHashMap<>();
        multiMatch.put("query", query);
        multiMatch.put("type", type);
        multiMatch.put("fields", fields);
        if (!isBlank(operator)) {
            multiMatch.put("operator", operator);
        }
        multiMatch.put("lenient", true);
        return Map.of("multi_match", multiMatch);
    }

    private List<String> cleanValues(List<String> values) {
        if (values == null || values.isEmpty()) {
            return List.of();
        }
        List<String> cleaned = new ArrayList<>();
        for (String value : values) {
            if (isBlank(value)) {
                continue;
            }
            String trimmed = value.trim();
            if (!cleaned.contains(trimmed)) {
                cleaned.add(trimmed);
            }
        }
        return cleaned;
    }

    private String firstValue(List<String> values) {
        if (values == null || values.isEmpty()) {
            return null;
        }
        for (String value : values) {
            if (!isBlank(value)) {
                return value.trim();
            }
        }
        return null;
    }

    private List<String> normalizeIsbnValues(List<String> values) {
        if (values == null || values.isEmpty()) {
            return List.of();
        }
        List<String> normalized = new ArrayList<>();
        for (String value : values) {
            String candidate = normalizeIsbn(value);
            if (candidate == null || candidate.isEmpty()) {
                continue;
            }
            if (!normalized.contains(candidate)) {
                normalized.add(candidate);
            }
        }
        return normalized;
    }

    private String normalizeIsbn(Object value) {
        String text;
        if (value instanceof Number number) {
            text = String.valueOf(number);
        } else if (value instanceof String raw) {
            text = raw;
        } else {
            return null;
        }
        if (text.isBlank()) {
            return null;
        }
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == 'x' || ch == 'X') {
                builder.append('X');
                continue;
            }
            if (Character.isDigit(ch)) {
                int numeric = Character.getNumericValue(ch);
                if (numeric >= 0 && numeric <= 9) {
                    builder.append((char) ('0' + numeric));
                }
            }
        }
        String normalized = builder.toString();
        return normalized.isEmpty() ? null : normalized;
    }

    private List<Map<String, Object>> buildFilters(QueryContextV1_1.RetrievalHints hints) {
        if (hints == null || hints.getFilters() == null) {
            return Collections.emptyList();
        }
        List<Map<String, Object>> filters = new ArrayList<>();
        for (QueryContextV1_1.Filter filter : hints.getFilters()) {
            if (filter == null || filter.getAnd() == null) {
                continue;
            }
            for (QueryContextV1_1.Constraint constraint : filter.getAnd()) {
                Map<String, Object> mapped = mapConstraint(constraint);
                if (mapped != null) {
                    filters.add(mapped);
                }
            }
        }
        return filters;
    }

    private Map<String, Object> mapConstraint(QueryContextV1_1.Constraint constraint) {
        if (constraint == null) {
            return null;
        }
        String scope = constraint.getScope();
        if (scope != null && !scope.equalsIgnoreCase("CATALOG")) {
            return null;
        }
        String op = constraint.getOp();
        if (op != null && !op.equalsIgnoreCase("eq")) {
            return null;
        }
        String logicalField = constraint.getLogicalField();
        if (logicalField == null) {
            return null;
        }
        Object value = constraint.getValue();
        if (value == null) {
            return null;
        }

        String normalized = logicalField.trim().toLowerCase(Locale.ROOT);
        if ("volume".equals(normalized)) {
            Integer volume = parseInteger(value);
            return volume == null ? null : Map.of("term", Map.of("volume", volume));
        }
        if ("edition_label".equals(normalized) || "edition_labels".equals(normalized)) {
            if (value instanceof List<?> values) {
                return Map.of("terms", Map.of("edition_labels", values));
            }
            return Map.of("term", Map.of("edition_labels", value));
        }
        if ("isbn13".equals(normalized)) {
            if (value instanceof List<?> values) {
                List<String> isbnValues = new ArrayList<>();
                for (Object entry : values) {
                    String normalizedIsbn = normalizeIsbn(entry);
                    if (normalizedIsbn != null && !isbnValues.contains(normalizedIsbn)) {
                        isbnValues.add(normalizedIsbn);
                    }
                }
                if (isbnValues.isEmpty()) {
                    return null;
                }
                return Map.of("terms", Map.of("identifiers.isbn13", isbnValues));
            }
            String normalizedIsbn = normalizeIsbn(value);
            return normalizedIsbn == null ? null : Map.of("term", Map.of("identifiers.isbn13", normalizedIsbn));
        }
        if ("language_code".equals(normalized)) {
            return Map.of("term", Map.of("language_code", value));
        }
        if ("kdc_node_id".equals(normalized) || "kdc_node_ids".equals(normalized)) {
            if (value instanceof List<?> values) {
                return Map.of("terms", Map.of("kdc_node_id", values));
            }
            return Map.of("term", Map.of("kdc_node_id", value));
        }
        if ("kdc_code".equals(normalized) || "kdc_codes".equals(normalized)) {
            if (value instanceof List<?> values) {
                return Map.of("terms", Map.of("kdc_code", values));
            }
            return Map.of("term", Map.of("kdc_code", value));
        }
        if ("kdc_path_codes".equals(normalized)) {
            if (value instanceof List<?> values) {
                return Map.of("terms", Map.of("kdc_path_codes", values));
            }
            return Map.of("term", Map.of("kdc_path_codes", value));
        }
        if ("kdc_edition".equals(normalized)) {
            return Map.of("term", Map.of("kdc_edition", value));
        }
        return null;
    }

    private Integer parseInteger(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value instanceof String text) {
            try {
                return Integer.parseInt(text.trim());
            } catch (NumberFormatException e) {
                return null;
            }
        }
        return null;
    }

    private FallbackApplication applyFallback(ExecutionPlan plan, Trigger trigger) {
        if (plan.fallbackPolicy == null || plan.fallbackPolicy.isEmpty()) {
            return FallbackApplication.notApplied();
        }
        for (QueryContextV1_1.FallbackPolicy policy : plan.fallbackPolicy) {
            if (policy == null || policy.getWhen() == null) {
                continue;
            }
            if (matchesTrigger(policy.getWhen(), trigger)) {
                ExecutionPlan mutated = new ExecutionPlan(plan);
                applyMutations(mutated, policy.getMutations());
                return new FallbackApplication(policy.getId(), mutated);
            }
        }
        return FallbackApplication.notApplied();
    }

    private boolean matchesTrigger(QueryContextV1_1.When when, Trigger trigger) {
        if (when == null) {
            return false;
        }
        return switch (trigger) {
            case VECTOR_ERROR -> Boolean.TRUE.equals(when.getOnVectorError()) || Boolean.TRUE.equals(when.getOnTimeout());
            case RERANK_ERROR -> Boolean.TRUE.equals(when.getOnRerankError()) || Boolean.TRUE.equals(when.getOnRerankTimeout());
            case ZERO_RESULTS -> Boolean.TRUE.equals(when.getOnZeroResults());
        };
    }

    private void applyMutations(ExecutionPlan plan, QueryContextV1_1.Mutations mutations) {
        if (mutations == null) {
            return;
        }
        if (mutations.getDisable() != null) {
            for (String disable : mutations.getDisable()) {
                if (disable == null) {
                    continue;
                }
                String normalized = disable.trim().toLowerCase(Locale.ROOT);
                if ("vector".equals(normalized)) {
                    plan.vectorEnabled = false;
                } else if ("rerank".equals(normalized)) {
                    plan.rerankEnabled = false;
                }
            }
        }
        if (!isBlank(mutations.getUseQueryTextSource())) {
            if (plan.context != null) {
                QueryTextSelection selection = selectQueryText(plan.context.getQuery(), mutations.getUseQueryTextSource());
                if (!isBlank(selection.text)) {
                    plan.queryText = selection.text;
                    plan.queryTextSourceUsed = selection.sourceUsed;
                }
            }
        }
        if (mutations.getAdjustHint() != null && mutations.getAdjustHint().getLexical() != null
            && mutations.getAdjustHint().getLexical().getTopK() != null) {
            plan.lexicalTopK = clamp(
                mutations.getAdjustHint().getLexical().getTopK(),
                QC_LEX_TOP_K_MIN,
                QC_LEX_TOP_K_MAX
            );
        }
    }

    private String resolveQcStrategy(ExecutionPlan plan, String appliedFallbackId) {
        String base;
        if (appliedFallbackId != null && !plan.vectorEnabled) {
            base = "hybrid_rrf_v1_1_fallback_lexical";
        } else if (plan.lexicalEnabled && plan.vectorEnabled) {
            base = "hybrid_rrf_v1_1";
        } else if (plan.lexicalEnabled) {
            base = "bm25_v1_1";
        } else {
            base = "hybrid_rrf_v1_1";
        }
        return applyFusionSuffix(base, plan);
    }

    private String resolveLegacyStrategy(ExecutionPlan plan) {
        String base = plan.vectorEnabled ? "hybrid_rrf_v1" : "bm25_v1";
        return applyFusionSuffix(base, plan);
    }

    private String applyFusionSuffix(String base, ExecutionPlan plan) {
        if (base == null) {
            return null;
        }
        if (plan != null && plan.fusionMethod == FusionMethod.WEIGHTED && base.contains("rrf")) {
            return base.replace("rrf", "weighted");
        }
        return base;
    }

    private String normalizeOperator(String operator) {
        if (operator == null || operator.trim().isEmpty()) {
            return "and";
        }
        String normalized = operator.trim().toLowerCase(Locale.ROOT);
        if ("or".equals(normalized)) {
            return "or";
        }
        return "and";
    }

    private boolean applyStrategy(boolean enableVector, String strategy) {
        if (strategy == null || strategy.trim().isEmpty()) {
            return enableVector;
        }
        String normalized = strategy.trim().toLowerCase(Locale.ROOT).replace('_', '-');
        if (normalized.contains("bm25")) {
            return false;
        }
        if (normalized.contains("hybrid")) {
            return enableVector;
        }
        return enableVector;
    }

    private int clamp(int value, int min, int max) {
        if (value < min) {
            return min;
        }
        if (value > max) {
            return max;
        }
        return value;
    }

    private String firstNonBlank(String... values) {
        if (values == null) {
            return null;
        }
        for (String value : values) {
            if (!isBlank(value)) {
                return value;
            }
        }
        return null;
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private String blankToNull(String value) {
        return isBlank(value) ? null : value;
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private static class EnhanceOutcome {
        private boolean attempted;
        private boolean applied;
        private String reason;
        private String decision;
        private String strategy;
        private String finalQuery;
        private String finalSource;
        private boolean improved;
        private String skipReason;
        private RetrievalResult retryRetrieval;

        private static EnhanceOutcome notAttempted() {
            return new EnhanceOutcome();
        }

        private static EnhanceOutcome attempted(String reason) {
            EnhanceOutcome outcome = new EnhanceOutcome();
            outcome.attempted = true;
            outcome.reason = reason;
            return outcome;
        }

        private static EnhanceOutcome skipped(String reason, String skipReason) {
            EnhanceOutcome outcome = attempted(reason);
            outcome.skipReason = skipReason;
            return outcome;
        }
    }

    private static class ExecutionPlan {
        private final QueryContextV1_1 context;
        private String queryText;
        private String queryTextSourceUsed;
        private boolean lexicalEnabled;
        private boolean vectorEnabled;
        private boolean rerankEnabled;
        private int lexicalTopK;
        private int vectorTopK;
        private int rerankTopK;
        private int rrfK;
        private FusionMethod fusionMethod;
        private String lexicalOperator;
        private String minimumShouldMatch;
        private List<String> lexicalFields;
        private Map<String, Object> lexicalQueryOverride;
        private List<Map<String, Object>> filters;
        private List<QueryContextV1_1.FallbackPolicy> fallbackPolicy;
        private Map<String, Double> boost;
        private Integer timeBudgetMs;
        private Integer lexicalBudgetMs;
        private Integer vectorBudgetMs;
        private Integer rerankBudgetMs;
        private boolean debugEnabled;
        private boolean explainEnabled;
        private String experimentBucket;
        private boolean exploreApplied;

        private ExecutionPlan(QueryContextV1_1 context) {
            this.context = context;
            this.filters = Collections.emptyList();
            this.fallbackPolicy = Collections.emptyList();
        }

        private ExecutionPlan(ExecutionPlan other) {
            this.context = other.context;
            this.queryText = other.queryText;
            this.queryTextSourceUsed = other.queryTextSourceUsed;
            this.lexicalEnabled = other.lexicalEnabled;
            this.vectorEnabled = other.vectorEnabled;
            this.rerankEnabled = other.rerankEnabled;
            this.lexicalTopK = other.lexicalTopK;
            this.vectorTopK = other.vectorTopK;
            this.rerankTopK = other.rerankTopK;
            this.rrfK = other.rrfK;
            this.fusionMethod = other.fusionMethod;
            this.lexicalOperator = other.lexicalOperator;
            this.minimumShouldMatch = other.minimumShouldMatch;
            this.lexicalFields = other.lexicalFields;
            this.lexicalQueryOverride = other.lexicalQueryOverride;
            this.filters = other.filters;
            this.fallbackPolicy = other.fallbackPolicy;
            this.boost = other.boost;
            this.timeBudgetMs = other.timeBudgetMs;
            this.lexicalBudgetMs = other.lexicalBudgetMs;
            this.vectorBudgetMs = other.vectorBudgetMs;
            this.rerankBudgetMs = other.rerankBudgetMs;
            this.debugEnabled = other.debugEnabled;
            this.explainEnabled = other.explainEnabled;
            this.experimentBucket = other.experimentBucket;
            this.exploreApplied = other.exploreApplied;
        }
    }

    private static class RetrievalResult {
        private final List<RrfFusion.Candidate> fused;
        private final Map<String, JsonNode> sources;
        private final RetrievalStageResult lexical;
        private final RetrievalStageResult vector;
        private final long fusionTookMs;

        private RetrievalResult(
            List<RrfFusion.Candidate> fused,
            Map<String, JsonNode> sources,
            RetrievalStageResult lexical,
            RetrievalStageResult vector,
            long fusionTookMs
        ) {
            this.fused = fused;
            this.sources = sources;
            this.lexical = lexical;
            this.vector = vector;
            this.fusionTookMs = fusionTookMs;
        }
    }

    private static class RerankOutcome {
        private final List<BookHit> hits;
        private final boolean rankingApplied;
        private final boolean rerankError;
        private final boolean rerankTimedOut;
        private final long tookMs;
        private final String errorMessage;
        private final String skipReason;

        private RerankOutcome(
            List<BookHit> hits,
            boolean rankingApplied,
            boolean rerankError,
            boolean rerankTimedOut,
            long tookMs,
            String errorMessage,
            String skipReason
        ) {
            this.hits = hits;
            this.rankingApplied = rankingApplied;
            this.rerankError = rerankError;
            this.rerankTimedOut = rerankTimedOut;
            this.tookMs = tookMs;
            this.errorMessage = errorMessage;
            this.skipReason = skipReason;
        }
    }

    private static class QueryTextSelection {
        private final String text;
        private final String sourceUsed;

        private QueryTextSelection(String text, String sourceUsed) {
            this.text = text;
            this.sourceUsed = sourceUsed;
        }
    }

    private static class FallbackApplication {
        private final String id;
        private final ExecutionPlan plan;
        private final boolean applied;

        private FallbackApplication(String id, ExecutionPlan plan) {
            this.id = id;
            this.plan = plan;
            this.applied = true;
        }

        private static FallbackApplication notApplied() {
            return new FallbackApplication(null, null, false);
        }

        private FallbackApplication(String id, ExecutionPlan plan, boolean applied) {
            this.id = id;
            this.plan = plan;
            this.applied = applied;
        }
    }

    private enum Trigger {
        VECTOR_ERROR,
        RERANK_ERROR,
        ZERO_RESULTS
    }

    private BookHit.Source mapSource(JsonNode source, String docId) {
        if (source == null || source.isMissingNode()) {
            return null;
        }
        BookHit.Source mapped = new BookHit.Source();
        mapped.setTitleKo(readTitle(source));
        mapped.setPublisherName(readText(source, "publisher_name"));
        mapped.setIssuedYear(readInteger(source, "issued_year"));
        mapped.setVolume(readInteger(source, "volume"));
        mapped.setEditionLabels(extractEditionLabels(source));
        mapped.setKdcCode(readText(source, "kdc_code"));
        mapped.setKdcPathCodes(extractTextArray(source, "kdc_path_codes"));
        mapped.setIsbn13(extractIsbn13(source));
        mapped.setAuthors(extractAuthors(source));
        mapped.setCoverUrl(resolveCoverUrl(source, docId, mapped.getTitleKo(), mapped.getIsbn13()));
        return mapped;
    }

    private String resolveCoverUrl(JsonNode source, String docId, String title, String isbn13) {
        String direct = firstNonBlank(
            readText(source, "cover_url"),
            readText(source, "cover_image_url"),
            readText(source, "thumbnail_url"),
            readText(source, "image_url")
        );
        if (direct != null) {
            return direct;
        }
        JsonNode identifiers = source == null ? null : source.path("identifiers");
        if (identifiers != null && identifiers.isObject()) {
            String nested = firstNonBlank(
                textOrNull(identifiers.path("cover_url")),
                textOrNull(identifiers.path("thumbnail_url")),
                textOrNull(identifiers.path("image_url"))
            );
            if (nested != null) {
                return nested;
            }
        }
        return buildGeneratedCoverDataUrl(docId, title, isbn13);
    }

    private String buildGeneratedCoverDataUrl(String docId, String title, String isbn13) {
        String seed = firstNonBlank(docId, isbn13, title, "bsl-book-cover");
        int hash = Math.abs(seed.hashCode());

        String[] tones = {
            "#2f3d66,#5a7bb8",
            "#3f4f4a,#6d8f7e",
            "#5a3f2f,#a47f62",
            "#2f4f5a,#5f96ad",
            "#4c3d62,#7f6ab8",
            "#2f4b5f,#5f7fa6",
        };
        String[] picked = tones[hash % tones.length].split(",");
        String bgStart = picked[0];
        String bgEnd = picked[1];

        String resolvedTitle = sanitizeCoverText(firstNonBlank(title, docId, "제목 없음"), 40);
        String shortId = sanitizeCoverText(firstNonBlank(docId, "BSL"), 12);
        String line1 = escapeXml(cutTitleLine(resolvedTitle, 0, 12));
        String line2 = escapeXml(cutTitleLine(resolvedTitle, 12, 24));
        String line3 = escapeXml(cutTitleLine(resolvedTitle, 24, 36));
        String idLabel = escapeXml(shortId);

        String svg = "<svg xmlns='http://www.w3.org/2000/svg' width='360' height='520' viewBox='0 0 360 520'>"
            + "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            + "<stop offset='0%' stop-color='" + bgStart + "'/>"
            + "<stop offset='100%' stop-color='" + bgEnd + "'/>"
            + "</linearGradient></defs>"
            + "<rect width='360' height='520' fill='url(#g)'/>"
            + "<rect x='26' y='26' width='308' height='468' rx='22' fill='rgba(255,255,255,0.08)'/>"
            + "<text x='38' y='82' fill='rgba(255,255,255,0.9)' font-size='20' font-weight='700'>BSL BOOKS</text>"
            + "<text x='38' y='206' fill='#ffffff' font-size='40' font-weight='700'>" + line1 + "</text>"
            + "<text x='38' y='256' fill='#ffffff' font-size='40' font-weight='700'>" + line2 + "</text>"
            + "<text x='38' y='306' fill='#ffffff' font-size='40' font-weight='700'>" + line3 + "</text>"
            + "<text x='38' y='472' fill='rgba(255,255,255,0.86)' font-size='18' font-weight='600'>" + idLabel + "</text>"
            + "</svg>";

        return "data:image/svg+xml;utf8," + URLEncoder.encode(svg, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private String cutTitleLine(String title, int start, int end) {
        if (title == null || title.isBlank() || start >= title.length()) {
            return "";
        }
        int safeEnd = Math.min(end, title.length());
        return title.substring(start, safeEnd);
    }

    private String sanitizeCoverText(String value, int maxLen) {
        if (value == null) {
            return "";
        }
        String compact = value.replaceAll("\\s+", " ").trim();
        if (compact.isBlank()) {
            return "";
        }
        if (compact.length() <= maxLen) {
            return compact;
        }
        return compact.substring(0, maxLen);
    }

    private String escapeXml(String value) {
        if (value == null || value.isBlank()) {
            return "";
        }
        return value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;");
    }

    private String textOrNull(JsonNode node) {
        if (node == null || node.isNull() || node.isMissingNode()) {
            return null;
        }
        String value = node.asText(null);
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private String extractIsbn13(JsonNode source) {
        if (source == null || source.isMissingNode()) {
            return null;
        }
        JsonNode identifiers = source.path("identifiers");
        if (identifiers.isMissingNode() || identifiers.isNull()) {
            return null;
        }
        String value = identifiers.path("isbn13").asText(null);
        if (value == null || value.isBlank()) {
            return null;
        }
        return value;
    }

    private Integer readInteger(JsonNode source, String fieldName) {
        JsonNode node = source.path(fieldName);
        if (node.isMissingNode() || node.isNull()) {
            return null;
        }
        return node.asInt();
    }

    private List<String> extractEditionLabels(JsonNode source) {
        return extractTextArray(source, "edition_labels");
    }

    private List<String> extractTextArray(JsonNode source, String fieldName) {
        List<String> values = new ArrayList<>();
        if (source == null || source.isMissingNode() || fieldName == null) {
            return values;
        }
        for (JsonNode node : source.path(fieldName)) {
            if (!node.isTextual()) {
                continue;
            }
            String value = node.asText(null);
            if (value != null && !value.isBlank()) {
                values.add(value);
            }
        }
        return values;
    }

    private String readText(JsonNode source, String fieldName) {
        if (source == null || source.isMissingNode() || fieldName == null) {
            return null;
        }
        String value = source.path(fieldName).asText(null);
        if (value == null || value.isBlank()) {
            return null;
        }
        return value;
    }

    private String readTitle(JsonNode source) {
        String titleKo = readText(source, "title_ko");
        if (titleKo != null) {
            return titleKo;
        }
        return readText(source, "title_en");
    }

    private List<String> extractAuthors(JsonNode source) {
        List<String> authors = new ArrayList<>();
        JsonNode authorsNode = source == null ? null : source.path("authors");
        if (authorsNode == null || !authorsNode.isArray()) {
            return authors;
        }
        for (JsonNode authorNode : authorsNode) {
            if (authorNode.isTextual()) {
                String value = authorNode.asText(null);
                if (value != null && !value.isBlank()) {
                    authors.add(value);
                }
            } else if (authorNode.isObject()) {
                String nameKo = authorNode.path("name_ko").asText(null);
                String nameEn = authorNode.path("name_en").asText(null);
                if (nameKo != null && !nameKo.isBlank()) {
                    authors.add(nameKo);
                } else if (nameEn != null && !nameEn.isBlank()) {
                    authors.add(nameEn);
                }
            }
        }
        return authors;
    }

    private String buildDocText(String docId, JsonNode source) {
        if (source == null || source.isMissingNode()) {
            return docId;
        }
        List<String> parts = new ArrayList<>();
        String titleKo = readText(source, "title_ko");
        String titleEn = readText(source, "title_en");
        if (titleKo != null && !titleKo.isBlank()) {
            parts.add(titleKo);
        }
        if (titleEn != null && !titleEn.isBlank() && !titleEn.equals(titleKo)) {
            parts.add(titleEn);
        }

        List<String> authors = extractAuthors(source);
        if (!authors.isEmpty()) {
            parts.add(String.join(", ", authors));
        }

        String publisher = readText(source, "publisher_name");
        if (publisher != null && !publisher.isBlank()) {
            parts.add(publisher);
        }
        String series = readText(source, "series_name");
        if (series != null && !series.isBlank()) {
            parts.add(series);
        }

        if (parts.isEmpty()) {
            return docId;
        }
        String text = String.join(" | ", parts);
        return text.isBlank() ? docId : text;
    }
}
