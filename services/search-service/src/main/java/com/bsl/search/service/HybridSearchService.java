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
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
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
import org.springframework.stereotype.Service;

@Service
public class HybridSearchService {
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
        MaterialGroupingService groupingService
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
        response.setSource(mapSource(source));
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
        if (isBlank(plan.queryText)) {
            throw new InvalidSearchRequestException("query text is required");
        }
        assignExperimentBucket(plan, requestId);

        String cacheKey = buildSerpCacheKey(plan, from, size);
        Optional<SearchResponse> cachedResponse = maybeServeSerpCache(cacheKey, traceId, requestId, started, plan);
        if (cachedResponse.isPresent()) {
            return cachedResponse.get();
        }

        RetrievalResult retrieval = retrieveCandidates(plan, requestId);
        RerankOutcome rerankOutcome = applyRerank(
            plan,
            retrieval,
            from,
            size,
            traceId,
            requestId,
            traceparent
        );

        SearchResponse.Debug debug = buildDebug(plan, retrieval, rerankOutcome, null, cacheKey, false);
        List<BookHit> finalHits = maybeApplyExploration(plan, rerankOutcome.hits, from, size, requestId, debug);
        finalHits = groupingService.apply(plan.queryText, finalHits, size);
        SearchResponse response = buildResponse(
            started,
            traceId,
            requestId,
            finalHits,
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
        if (isBlank(plan.queryText)) {
            throw new InvalidSearchRequestException("query text is required");
        }
        assignExperimentBucket(plan, requestId);

        String appliedFallbackId = null;
        String cacheKey = buildSerpCacheKey(plan, from, size);
        Optional<SearchResponse> cachedResponse = maybeServeSerpCache(cacheKey, traceId, requestId, started, plan);
        if (cachedResponse.isPresent()) {
            return cachedResponse.get();
        }

        RetrievalResult retrieval = retrieveCandidates(plan, requestId);

        if (retrieval.vector.isError() || retrieval.vector.isTimedOut()) {
            FallbackApplication fallback = applyFallback(plan, Trigger.VECTOR_ERROR);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(plan, requestId);
            }
        }

        if (retrieval.fused.isEmpty() && appliedFallbackId == null) {
            FallbackApplication fallback = applyFallback(plan, Trigger.ZERO_RESULTS);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(plan, requestId);
            }
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
                retrieval = retrieveCandidates(plan, requestId);
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
        SearchResponse.Debug debug = buildDebug(plan, retrieval, rerankOutcome, appliedFallbackId, cacheKey, false);
        List<BookHit> finalHits = maybeApplyExploration(plan, rerankOutcome.hits, from, size, requestId, debug);
        finalHits = groupingService.apply(plan.queryText, finalHits, size);

        SearchResponse response = buildResponse(
            started,
            traceId,
            requestId,
            finalHits,
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

            JsonNode source = sources.get(candidate.getDocId());
            if (source != null && !source.isMissingNode()) {
                features.setIssuedYear(readInteger(source, "issued_year"));
                features.setVolume(readInteger(source, "volume"));
                features.setEditionLabels(extractEditionLabels(source));
            } else {
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
            hit.setSource(mapSource(sources.get(docId)));
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

            hit.setSource(mapSource(sources.get(candidate.getDocId())));
            hits.add(hit);
        }
        return hits;
    }

    private RetrievalResult retrieveCandidates(ExecutionPlan plan, String requestId) {
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
            plan.debugEnabled,
            plan.explainEnabled
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
            plan.debugEnabled,
            plan.explainEnabled
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

        long fusionStarted = System.nanoTime();
        FusionMethod fusionMethod = resolveFusionMethod(plan, requestId);
        List<RrfFusion.Candidate> fused = fuseCandidates(lexRanks, vecRanks, plan, fusionMethod);
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

        return new RetrievalResult(fused, sources, lexicalResult, vectorResult, fusionTookMs);
    }

    private List<RrfFusion.Candidate> fuseCandidates(
        Map<String, Integer> lexRanks,
        Map<String, Integer> vecRanks,
        ExecutionPlan plan,
        FusionMethod method
    ) {
        int k = plan.rrfK;
        if (method == FusionMethod.WEIGHTED) {
            double lexWeight = fusionPolicy == null ? 1.0 : fusionPolicy.getLexWeight();
            double vecWeight = fusionPolicy == null ? 1.0 : fusionPolicy.getVecWeight();
            return WeightedFusion.fuse(lexRanks, vecRanks, k, lexWeight, vecWeight);
        }
        return RrfFusion.fuse(lexRanks, vecRanks, k);
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

    private RerankOutcome applyRerank(
        ExecutionPlan plan,
        RetrievalResult retrieval,
        int from,
        int size,
        String traceId,
        String requestId,
        String traceparent
    ) {
        if (!plan.rerankEnabled || retrieval.fused.isEmpty() || plan.rerankTopK <= 0) {
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                false,
                false,
                0L,
                null
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
                "rerank_circuit_open"
            );
        }

        int limit = Math.min(plan.rerankTopK, retrieval.fused.size());
        List<RrfFusion.Candidate> rerankSlice = retrieval.fused.subList(0, limit);
        List<RerankRequest.Candidate> rerankCandidates = buildRerankCandidates(rerankSlice, retrieval.sources);
        Map<String, RrfFusion.Candidate> fusedById = toCandidateMap(retrieval.fused);

        CompletableFuture<RerankResponse> future = CompletableFuture.supplyAsync(
            () -> rankingGateway.rerank(plan.queryText, rerankCandidates, limit, traceId, requestId, traceparent),
            searchExecutor
        );

        long started = System.nanoTime();
        int timeoutMs = resolveRerankTimeoutMs(plan);
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
                "rerank_empty"
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
                "rerank_timeout"
            );
        } catch (ExecutionException e) {
            rerankBreaker.recordFailure();
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                false,
                0L,
                errorMessage(e)
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
                "rerank_interrupted"
            );
        } catch (RankingUnavailableException e) {
            rerankBreaker.recordFailure();
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true,
                false,
                0L,
                e.getMessage()
            );
        }
    }

    private SearchResponse buildResponse(
        long started,
        String traceId,
        String requestId,
        List<BookHit> hits,
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
        plan.lexicalBudgetMs = timeBudgetMs;
        plan.vectorBudgetMs = timeBudgetMs;
        plan.rerankBudgetMs = timeBudgetMs;

        plan.debugEnabled = Boolean.TRUE.equals(options.getDebug());
        plan.explainEnabled = Boolean.TRUE.equals(options.getExplain());
        return plan;
    }

    private SearchResponse.Debug buildDebug(
        ExecutionPlan plan,
        RetrievalResult retrieval,
        RerankOutcome rerankOutcome,
        String appliedFallbackId,
        String cacheKey,
        boolean cacheHit
    ) {
        boolean include = plan.debugEnabled || plan.explainEnabled || appliedFallbackId != null || cacheHit;
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
        stage.setErrorMessage(rerankOutcome.errorMessage);
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
            } else {
                warnings.add("vector_skipped");
            }
        }
        if (retrieval.vector.isError()) {
            warnings.add("vector_error");
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
        SearchResponse.Debug debug = buildDebug(plan, emptyRetrieval(plan), emptyRerankOutcome(), null, cacheKey, true);
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
        return new RerankOutcome(List.of(), false, false, false, 0L, null);
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

        QueryContextV1_1.Lexical lexical = hints == null ? null : hints.getLexical();
        plan.lexicalEnabled = lexical == null || lexical.getEnabled() == null || lexical.getEnabled();
        plan.lexicalTopK = lexical != null && lexical.getTopKHint() != null
            ? clamp(lexical.getTopKHint(), QC_LEX_TOP_K_MIN, QC_LEX_TOP_K_MAX)
            : DEFAULT_QC_LEX_TOP_K;
        plan.lexicalOperator = normalizeOperator(lexical == null ? null : lexical.getOperator());
        plan.minimumShouldMatch = blankToNull(lexical == null ? null : lexical.getMinimumShouldMatch());
        plan.lexicalFields = mapPreferredFields(lexical == null ? null : lexical.getPreferredLogicalFields());

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
                mapped.add("title_ko");
            } else if ("title_ko.edge".equals(normalized)) {
                mapped.add("title_ko.edge");
            } else if ("author_ko".equals(normalized)) {
                mapped.add("authors.name_ko");
            } else if ("series_ko".equals(normalized)) {
                mapped.add("series_name");
            }
        }
        return mapped.isEmpty() ? null : mapped;
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
            return Map.of("term", Map.of("identifiers.isbn13", value));
        }
        if ("language_code".equals(normalized)) {
            return Map.of("term", Map.of("language_code", value));
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

        private RerankOutcome(
            List<BookHit> hits,
            boolean rankingApplied,
            boolean rerankError,
            boolean rerankTimedOut,
            long tookMs,
            String errorMessage
        ) {
            this.hits = hits;
            this.rankingApplied = rankingApplied;
            this.rerankError = rerankError;
            this.rerankTimedOut = rerankTimedOut;
            this.tookMs = tookMs;
            this.errorMessage = errorMessage;
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

    private BookHit.Source mapSource(JsonNode source) {
        if (source == null || source.isMissingNode()) {
            return null;
        }
        BookHit.Source mapped = new BookHit.Source();
        mapped.setTitleKo(source.path("title_ko").asText(null));
        mapped.setPublisherName(source.path("publisher_name").asText(null));
        mapped.setIssuedYear(readInteger(source, "issued_year"));
        mapped.setVolume(readInteger(source, "volume"));
        mapped.setEditionLabels(extractEditionLabels(source));

        List<String> authors = new ArrayList<>();
        JsonNode authorsNode = source.path("authors");
        if (authorsNode.isArray()) {
            for (JsonNode authorNode : authorsNode) {
                if (authorNode.isTextual()) {
                    authors.add(authorNode.asText());
                } else if (authorNode.isObject()) {
                    String nameKo = authorNode.path("name_ko").asText(null);
                    String nameEn = authorNode.path("name_en").asText(null);
                    if (nameKo != null && !nameKo.isEmpty()) {
                        authors.add(nameKo);
                    } else if (nameEn != null && !nameEn.isEmpty()) {
                        authors.add(nameEn);
                    }
                }
            }
        }
        mapped.setAuthors(authors);
        return mapped;
    }

    private Integer readInteger(JsonNode source, String fieldName) {
        JsonNode node = source.path(fieldName);
        if (node.isMissingNode() || node.isNull()) {
            return null;
        }
        return node.asInt();
    }

    private List<String> extractEditionLabels(JsonNode source) {
        List<String> editionLabels = new ArrayList<>();
        for (JsonNode labelNode : source.path("edition_labels")) {
            if (labelNode.isTextual()) {
                editionLabels.add(labelNode.asText());
            }
        }
        return editionLabels;
    }
}
