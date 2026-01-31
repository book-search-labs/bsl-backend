package com.bsl.search.retrieval;

import com.bsl.search.embed.EmbeddingProvider;
import com.bsl.search.embed.EmbeddingUnavailableException;
import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchQueryResult;
import com.bsl.search.opensearch.OpenSearchRequestException;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class VectorRetriever implements Retriever {
    private final OpenSearchGateway openSearchGateway;
    private final EmbeddingProvider embeddingProvider;
    private final VectorSearchProperties properties;

    public VectorRetriever(
        OpenSearchGateway openSearchGateway,
        EmbeddingProvider embeddingProvider,
        VectorSearchProperties properties
    ) {
        this.openSearchGateway = openSearchGateway;
        this.embeddingProvider = embeddingProvider;
        this.properties = properties;
    }

    @Override
    public String name() {
        return "vector";
    }

    public String mode() {
        return properties.getMode() == null ? null : properties.getMode().name().toLowerCase();
    }

    @Override
    public RetrievalStageResult retrieve(RetrievalStageContext context) {
        if (context == null || context.getQueryText() == null || context.getQueryText().isBlank()) {
            return RetrievalStageResult.empty();
        }
        if (context.getTopK() <= 0) {
            return RetrievalStageResult.empty();
        }
        if (properties.getMode() == VectorSearchMode.DISABLED) {
            return RetrievalStageResult.skipped("vector_disabled");
        }

        long started = System.nanoTime();
        try {
            OpenSearchQueryResult result;
            if (properties.getMode() == VectorSearchMode.OPENSEARCH_NEURAL) {
                if (properties.getModelId() == null || properties.getModelId().isBlank()) {
                    return RetrievalStageResult.error("vector_model_id_missing");
                }
                result = openSearchGateway.searchVectorByTextDetailed(
                    context.getQueryText(),
                    context.getTopK(),
                    properties.getModelId(),
                    context.getTimeBudgetMs(),
                    context.getFilters(),
                    context.isExplain()
                );
            } else {
                List<Double> vector = embeddingProvider.embed(context.getQueryText(), context.getTimeBudgetMs());
                result = openSearchGateway.searchVectorDetailed(
                    vector,
                    context.getTopK(),
                    context.getTimeBudgetMs(),
                    context.getFilters(),
                    context.isExplain()
                );
            }

            List<String> docIds = result == null ? List.of() : result.getDocIds();
            Map<String, Object> queryDsl = context.isDebug() ? (result == null ? null : result.getQueryDsl()) : null;
            long tookMs = (System.nanoTime() - started) / 1_000_000L;
            return RetrievalStageResult.success(docIds, queryDsl, tookMs);
        } catch (EmbeddingUnavailableException e) {
            return RetrievalStageResult.error(e.getMessage());
        } catch (OpenSearchUnavailableException | OpenSearchRequestException e) {
            return RetrievalStageResult.error(e.getMessage());
        } catch (RuntimeException e) {
            return RetrievalStageResult.error(e.getMessage());
        }
    }
}
