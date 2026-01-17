package com.bsl.search.service;

import com.bsl.search.api.dto.BookHit;
import com.bsl.search.api.dto.Options;
import com.bsl.search.api.dto.QueryContext;
import com.bsl.search.api.dto.QueryContextV1_1;
import com.bsl.search.api.dto.SearchRequest;
import com.bsl.search.api.dto.SearchResponse;
import com.bsl.search.embed.ToyEmbedder;
import com.bsl.search.merge.RrfFusion;
import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchRequestException;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
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
    private final ToyEmbedder toyEmbedder;
    private final RankingGateway rankingGateway;

    public HybridSearchService(OpenSearchGateway openSearchGateway, ToyEmbedder toyEmbedder, RankingGateway rankingGateway) {
        this.openSearchGateway = openSearchGateway;
        this.toyEmbedder = toyEmbedder;
        this.rankingGateway = rankingGateway;
    }

    public SearchResponse search(SearchRequest request, String traceId, String requestId) {
        if (request == null) {
            throw new InvalidSearchRequestException("request body is required");
        }
        if (request.getQueryContextV1_1() != null) {
            return searchWithQcV11(request, traceId, requestId);
        }
        return searchLegacy(request, traceId, requestId);
    }

    private SearchResponse searchLegacy(SearchRequest request, String traceId, String requestId) {
        long started = System.nanoTime();

        Options options = request.getOptions() == null ? new Options() : request.getOptions();
        int size = options.getSize() != null ? Math.max(options.getSize(), 0) : DEFAULT_SIZE;
        int from = options.getFrom() != null ? Math.max(options.getFrom(), 0) : DEFAULT_FROM;
        boolean enableVector = options.getEnableVector() == null || options.getEnableVector();
        int rrfK = options.getRrfK() != null ? options.getRrfK() : DEFAULT_RRF_K;

        QueryContext queryContext = request.getQueryContext();
        QueryContext.RetrievalHints retrievalHints = queryContext == null ? null : queryContext.getRetrievalHints();

        String query = resolveLegacyQueryText(request, queryContext);
        if (isBlank(query)) {
            throw new InvalidSearchRequestException("query text is required");
        }

        int topK = DEFAULT_LEX_TOP_K;
        int vecTopK = DEFAULT_VEC_TOP_K;
        if (retrievalHints != null && retrievalHints.getTopK() != null) {
            topK = clamp(retrievalHints.getTopK(), MIN_TOP_K, MAX_TOP_K);
            vecTopK = topK;
        }

        Integer timeBudgetMs = null;
        if (retrievalHints != null && retrievalHints.getTimeBudgetMs() != null) {
            timeBudgetMs = clamp(retrievalHints.getTimeBudgetMs(), MIN_TIME_BUDGET_MS, MAX_TIME_BUDGET_MS);
        }

        boolean allowVector = applyStrategy(enableVector, retrievalHints == null ? null : retrievalHints.getStrategy());
        Map<String, Double> boost = retrievalHints == null ? null : retrievalHints.getBoost();

        RetrievalResult retrieval = retrieveCandidates(
            query,
            true,
            allowVector,
            topK,
            vecTopK,
            rrfK,
            boost,
            null,
            null,
            Collections.emptyList(),
            null,
            timeBudgetMs
        );

        RerankOutcome rerankOutcome = applyRerank(
            query,
            retrieval,
            from,
            size,
            Math.min(from + size, retrieval.fused.size()),
            true,
            traceId,
            requestId
        );

        SearchResponse response = buildResponse(
            started,
            traceId,
            requestId,
            rerankOutcome.hits,
            rerankOutcome.rankingApplied,
            "hybrid_rrf_v1",
            null
        );
        return response;
    }

    private SearchResponse searchWithQcV11(SearchRequest request, String traceId, String requestId) {
        long started = System.nanoTime();

        QueryContextV1_1 qc = request.getQueryContextV1_1();
        if (qc.getMeta() == null || qc.getMeta().getSchemaVersion() == null
            || !"qc.v1.1".equals(qc.getMeta().getSchemaVersion())) {
            throw new InvalidSearchRequestException("query_context_v1_1.meta.schemaVersion must be qc.v1.1");
        }

        Options options = request.getOptions() == null ? new Options() : request.getOptions();
        int size = options.getSize() != null ? Math.max(options.getSize(), 0) : DEFAULT_SIZE;
        int from = options.getFrom() != null ? Math.max(options.getFrom(), 0) : DEFAULT_FROM;

        ExecutionPlan plan = buildPlanFromQcV11(qc);
        if (isBlank(plan.queryText)) {
            throw new InvalidSearchRequestException("query text is required");
        }

        String appliedFallbackId = null;
        RetrievalResult retrieval = retrieveCandidates(
            plan.queryText,
            plan.lexicalEnabled,
            plan.vectorEnabled,
            plan.lexicalTopK,
            plan.vectorTopK,
            plan.rrfK,
            null,
            plan.lexicalOperator,
            plan.minimumShouldMatch,
            plan.filters,
            plan.lexicalFields,
            plan.timeBudgetMs
        );

        if (retrieval.vectorError) {
            FallbackApplication fallback = applyFallback(plan, Trigger.VECTOR_ERROR);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(
                    plan.queryText,
                    plan.lexicalEnabled,
                    plan.vectorEnabled,
                    plan.lexicalTopK,
                    plan.vectorTopK,
                    plan.rrfK,
                    null,
                    plan.lexicalOperator,
                    plan.minimumShouldMatch,
                    plan.filters,
                    plan.lexicalFields,
                    plan.timeBudgetMs
                );
            }
        }

        if (retrieval.fused.isEmpty() && appliedFallbackId == null) {
            FallbackApplication fallback = applyFallback(plan, Trigger.ZERO_RESULTS);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(
                    plan.queryText,
                    plan.lexicalEnabled,
                    plan.vectorEnabled,
                    plan.lexicalTopK,
                    plan.vectorTopK,
                    plan.rrfK,
                    null,
                    plan.lexicalOperator,
                    plan.minimumShouldMatch,
                    plan.filters,
                    plan.lexicalFields,
                    plan.timeBudgetMs
                );
            }
        }

        RerankOutcome rerankOutcome = applyRerank(
            plan.queryText,
            retrieval,
            from,
            size,
            Math.min(plan.rerankTopK, retrieval.fused.size()),
            plan.rerankEnabled,
            traceId,
            requestId
        );

        if (rerankOutcome.rerankError && appliedFallbackId == null) {
            FallbackApplication fallback = applyFallback(plan, Trigger.RERANK_ERROR);
            if (fallback.applied) {
                appliedFallbackId = fallback.id;
                plan = fallback.plan;
                retrieval = retrieveCandidates(
                    plan.queryText,
                    plan.lexicalEnabled,
                    plan.vectorEnabled,
                    plan.lexicalTopK,
                    plan.vectorTopK,
                    plan.rrfK,
                    null,
                    plan.lexicalOperator,
                    plan.minimumShouldMatch,
                    plan.filters,
                    plan.lexicalFields,
                    plan.timeBudgetMs
                );
                rerankOutcome = applyRerank(
                    plan.queryText,
                    retrieval,
                    from,
                    size,
                    Math.min(plan.rerankTopK, retrieval.fused.size()),
                    plan.rerankEnabled,
                    traceId,
                    requestId
                );
            }
        }

        String strategy = resolveQcStrategy(plan, appliedFallbackId);
        SearchResponse.Debug debug = new SearchResponse.Debug();
        debug.setAppliedFallbackId(appliedFallbackId);
        debug.setQueryTextSourceUsed(plan.queryTextSourceUsed);
        SearchResponse.Stages stages = new SearchResponse.Stages();
        stages.setLexical(plan.lexicalEnabled);
        stages.setVector(plan.vectorEnabled);
        stages.setRerank(plan.rerankEnabled);
        debug.setStages(stages);

        SearchResponse response = buildResponse(
            started,
            traceId,
            requestId,
            rerankOutcome.hits,
            rerankOutcome.rankingApplied,
            strategy,
            debug
        );
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

    private RetrievalResult retrieveCandidates(
        String query,
        boolean lexicalEnabled,
        boolean vectorEnabled,
        int lexicalTopK,
        int vectorTopK,
        int rrfK,
        Map<String, Double> boost,
        String operator,
        String minimumShouldMatch,
        List<Map<String, Object>> filters,
        List<String> fieldsOverride,
        Integer timeBudgetMs
    ) {
        List<String> lexicalDocIds = Collections.emptyList();
        if (lexicalEnabled) {
            lexicalDocIds = openSearchGateway.searchLexical(
                query,
                lexicalTopK,
                boost,
                timeBudgetMs,
                operator,
                minimumShouldMatch,
                filters,
                fieldsOverride
            );
        }
        Map<String, Integer> lexRanks = rankMap(lexicalDocIds);

        boolean vectorError = false;
        Map<String, Integer> vecRanks = Collections.emptyMap();
        if (vectorEnabled) {
            try {
                List<Double> vector = toyEmbedder.embed(query);
                List<String> vecDocIds = openSearchGateway.searchVector(vector, vectorTopK, timeBudgetMs, filters);
                vecRanks = rankMap(vecDocIds);
            } catch (OpenSearchUnavailableException | OpenSearchRequestException e) {
                vectorError = true;
                vecRanks = Collections.emptyMap();
            }
        }

        List<RrfFusion.Candidate> fused = RrfFusion.fuse(lexRanks, vecRanks, rrfK);
        List<String> fusedDocIds = toDocIds(fused);
        Map<String, JsonNode> sources = fusedDocIds.isEmpty()
            ? Collections.emptyMap()
            : openSearchGateway.mgetSources(fusedDocIds, timeBudgetMs);

        return new RetrievalResult(fused, sources, vectorError);
    }

    private RerankOutcome applyRerank(
        String query,
        RetrievalResult retrieval,
        int from,
        int size,
        int rerankSize,
        boolean rerankEnabled,
        String traceId,
        String requestId
    ) {
        if (!rerankEnabled || retrieval.fused.isEmpty() || rerankSize <= 0) {
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                false
            );
        }

        int limit = Math.min(rerankSize, retrieval.fused.size());
        List<RrfFusion.Candidate> rerankSlice = retrieval.fused.subList(0, limit);
        List<RerankRequest.Candidate> rerankCandidates = buildRerankCandidates(rerankSlice, retrieval.sources);
        Map<String, RrfFusion.Candidate> fusedById = toCandidateMap(retrieval.fused);

        try {
            RerankResponse rerankResponse = rankingGateway.rerank(
                query,
                rerankCandidates,
                limit,
                traceId,
                requestId
            );

            if (rerankResponse != null && rerankResponse.getHits() != null) {
                return new RerankOutcome(
                    buildHitsFromRanking(rerankResponse.getHits(), fusedById, from, size, retrieval.sources),
                    true,
                    false
                );
            }
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true
            );
        } catch (RankingUnavailableException e) {
            return new RerankOutcome(
                buildHitsFromFused(retrieval.fused, from, size, retrieval.sources),
                false,
                true
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

    private ExecutionPlan buildPlanFromQcV11(QueryContextV1_1 qc) {
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
        if (hints != null && hints.getExecutionHint() != null && hints.getExecutionHint().getTimeoutMs() != null) {
            timeoutMs = clamp(hints.getExecutionHint().getTimeoutMs(), QC_TIMEOUT_MIN_MS, QC_TIMEOUT_MAX_MS);
        }
        plan.timeBudgetMs = timeoutMs;

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
            QueryTextSelection selection = selectQueryText(plan.context.getQuery(), mutations.getUseQueryTextSource());
            if (!isBlank(selection.text)) {
                plan.queryText = selection.text;
                plan.queryTextSourceUsed = selection.sourceUsed;
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
        if (appliedFallbackId != null && !plan.vectorEnabled) {
            return "hybrid_rrf_v1_1_fallback_lexical";
        }
        if (plan.lexicalEnabled && plan.vectorEnabled) {
            return "hybrid_rrf_v1_1";
        }
        if (plan.lexicalEnabled) {
            return "bm25_v1_1";
        }
        return "hybrid_rrf_v1_1";
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
        private String lexicalOperator;
        private String minimumShouldMatch;
        private List<String> lexicalFields;
        private List<Map<String, Object>> filters;
        private List<QueryContextV1_1.FallbackPolicy> fallbackPolicy;
        private Integer timeBudgetMs;

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
            this.lexicalOperator = other.lexicalOperator;
            this.minimumShouldMatch = other.minimumShouldMatch;
            this.lexicalFields = other.lexicalFields;
            this.filters = other.filters;
            this.fallbackPolicy = other.fallbackPolicy;
            this.timeBudgetMs = other.timeBudgetMs;
        }
    }

    private static class RetrievalResult {
        private final List<RrfFusion.Candidate> fused;
        private final Map<String, JsonNode> sources;
        private final boolean vectorError;

        private RetrievalResult(List<RrfFusion.Candidate> fused, Map<String, JsonNode> sources, boolean vectorError) {
            this.fused = fused;
            this.sources = sources;
            this.vectorError = vectorError;
        }
    }

    private static class RerankOutcome {
        private final List<BookHit> hits;
        private final boolean rankingApplied;
        private final boolean rerankError;

        private RerankOutcome(List<BookHit> hits, boolean rankingApplied, boolean rerankError) {
            this.hits = hits;
            this.rankingApplied = rankingApplied;
            this.rerankError = rerankError;
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
