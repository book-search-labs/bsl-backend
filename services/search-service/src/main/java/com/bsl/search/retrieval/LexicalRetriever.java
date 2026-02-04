package com.bsl.search.retrieval;

import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchQueryResult;
import com.bsl.search.opensearch.OpenSearchRequestException;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
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
        boolean hasQuery = context.getQueryText() != null && !context.getQueryText().isBlank();
        boolean hasFilters = context.getFilters() != null && !context.getFilters().isEmpty();
        if (!hasQuery && !hasFilters) {
            return RetrievalStageResult.empty();
        }
        long started = System.nanoTime();
        try {
            OpenSearchQueryResult result = hasQuery
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
            List<String> docIds = result == null ? List.of() : result.getDocIds();
            Map<String, Object> queryDsl = context.isDebug() ? (result == null ? null : result.getQueryDsl()) : null;
            long tookMs = (System.nanoTime() - started) / 1_000_000L;
            return RetrievalStageResult.success(docIds, queryDsl, tookMs);
        } catch (OpenSearchUnavailableException | OpenSearchRequestException e) {
            return RetrievalStageResult.error(e.getMessage());
        }
    }
}
