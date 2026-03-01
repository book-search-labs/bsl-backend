package com.bsl.search.retrieval;

import com.fasterxml.jackson.databind.JsonNode;
import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchQueryResult;
import com.bsl.search.opensearch.OpenSearchRequestException;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class LexicalRetriever implements Retriever {
    private final OpenSearchGateway openSearchGateway;

    public LexicalRetriever(OpenSearchGateway openSearchGateway) {
        this.openSearchGateway = openSearchGateway;
    }

    @Override
    public String name() {
        return "lexical";
    }

    @Override
    public RetrievalStageResult retrieve(RetrievalStageContext context) {
        if (context == null) {
            return RetrievalStageResult.empty();
        }
        if (context.getTopK() <= 0) {
            return RetrievalStageResult.empty();
        }
        boolean hasQueryOverride = context.getQueryOverride() != null && !context.getQueryOverride().isEmpty();
        boolean hasQuery = context.getQueryText() != null && !context.getQueryText().isBlank();
        boolean hasFilters = context.getFilters() != null && !context.getFilters().isEmpty();
        if (!hasQueryOverride && !hasQuery && !hasFilters) {
            return RetrievalStageResult.empty();
        }
        long started = System.nanoTime();
        try {
            OpenSearchQueryResult result;
            if (hasQueryOverride) {
                result = openSearchGateway.searchLexicalByDslDetailed(
                    context.getQueryOverride(),
                    context.getTopK(),
                    context.getTimeBudgetMs(),
                    context.getFilters(),
                    context.isExplain()
                );
            } else {
                result = hasQuery
                    ? openSearchGateway.searchLexicalDetailed(
                        context.getQueryText(),
                        context.getTopK(),
                        context.getBoost(),
                        context.getTimeBudgetMs(),
                        context.getOperator(),
                        context.getMinimumShouldMatch(),
                        context.getFilters(),
                        context.getFieldsOverride(),
                        context.isExplain()
                    )
                    : openSearchGateway.searchMatchAllDetailed(
                        context.getTopK(),
                        context.getTimeBudgetMs(),
                        context.getFilters(),
                        context.isExplain()
                    );
            }
            if (shouldRunAuthorContainsFallback(context, hasQueryOverride, hasQuery, result)) {
                OpenSearchQueryResult fallback = openSearchGateway.searchAuthorContainsFallbackDetailed(
                    context.getQueryText(),
                    context.getTopK(),
                    context.getTimeBudgetMs(),
                    context.getFilters(),
                    context.isExplain()
                );
                if (fallback != null && !fallback.getDocIds().isEmpty()) {
                    result = fallback;
                }
            }
            List<String> docIds = result == null ? List.of() : result.getDocIds();
            Map<String, Double> scoresByDocId = result == null ? Map.of() : result.getScoresByDocId();
            Map<String, Object> queryDsl = context.isDebug() ? (result == null ? null : result.getQueryDsl()) : null;
            long tookMs = (System.nanoTime() - started) / 1_000_000L;
            return RetrievalStageResult.success(docIds, scoresByDocId, queryDsl, tookMs);
        } catch (OpenSearchUnavailableException | OpenSearchRequestException e) {
            return RetrievalStageResult.error(e.getMessage());
        }
    }

    private boolean shouldRunAuthorContainsFallback(
        RetrievalStageContext context,
        boolean hasQueryOverride,
        boolean hasQuery,
        OpenSearchQueryResult result
    ) {
        if (hasQueryOverride || !hasQuery) {
            return false;
        }
        String trimmed = context.getQueryText() == null ? "" : context.getQueryText().trim();
        if (trimmed.isEmpty() || trimmed.contains(" ")) {
            return false;
        }
        if (!containsHangul(trimmed)) {
            return false;
        }
        if (trimmed.length() < 2 || trimmed.length() > 4) {
            return false;
        }
        if (result == null || result.getDocIds().isEmpty()) {
            return true;
        }

        List<String> docIds = result.getDocIds();
        int probeSize = Math.min(docIds.size(), 20);
        List<String> probeIds = new ArrayList<>(docIds.subList(0, probeSize));
        Map<String, JsonNode> sources = openSearchGateway.mgetSources(probeIds, context.getTimeBudgetMs());

        if (containsQueryInSources(sources, trimmed, "author_names_ko")
            || containsQueryInSources(sources, trimmed, "author_names_en")) {
            return false;
        }
        if (containsQueryInSources(sources, trimmed, "title_ko")
            || containsQueryInSources(sources, trimmed, "title_en")
            || containsQueryInSources(sources, trimmed, "series_name")) {
            return false;
        }
        return true;
    }

    private boolean containsHangul(String text) {
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if ((ch >= '\u1100' && ch <= '\u11FF') || (ch >= '\u3130' && ch <= '\u318F') || (ch >= '\uAC00' && ch <= '\uD7AF')) {
                return true;
            }
        }
        return false;
    }

    private boolean containsQueryInSources(Map<String, JsonNode> sources, String query, String field) {
        if (sources == null || sources.isEmpty()) {
            return false;
        }
        String needle = query.toLowerCase();
        for (JsonNode source : sources.values()) {
            if (source == null || source.isNull() || !source.has(field)) {
                continue;
            }
            JsonNode value = source.path(field);
            if (value.isTextual()) {
                if (value.asText("").toLowerCase().contains(needle)) {
                    return true;
                }
                continue;
            }
            if (value.isArray()) {
                for (JsonNode item : value) {
                    if (item != null && item.isTextual() && item.asText("").toLowerCase().contains(needle)) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
}
