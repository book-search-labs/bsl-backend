package com.bsl.search.retrieval;

import java.util.Collections;
import java.util.List;
import java.util.Map;

public class RetrievalStageContext {
    private final String queryText;
    private final int topK;
    private final Map<String, Double> boost;
    private final Integer timeBudgetMs;
    private final String operator;
    private final String minimumShouldMatch;
    private final List<Map<String, Object>> filters;
    private final List<String> fieldsOverride;
    private final Map<String, Object> queryOverride;
    private final boolean debug;
    private final boolean explain;
    private final String traceId;
    private final String requestId;

    public RetrievalStageContext(
        String queryText,
        int topK,
        Map<String, Double> boost,
        Integer timeBudgetMs,
        String operator,
        String minimumShouldMatch,
        List<Map<String, Object>> filters,
        List<String> fieldsOverride,
        Map<String, Object> queryOverride,
        boolean debug,
        boolean explain,
        String traceId,
        String requestId
    ) {
        this.queryText = queryText;
        this.topK = topK;
        this.boost = boost == null ? Collections.emptyMap() : boost;
        this.timeBudgetMs = timeBudgetMs;
        this.operator = operator;
        this.minimumShouldMatch = minimumShouldMatch;
        this.filters = filters == null ? List.of() : filters;
        this.fieldsOverride = fieldsOverride;
        this.queryOverride = queryOverride;
        this.debug = debug;
        this.explain = explain;
        this.traceId = traceId;
        this.requestId = requestId;
    }

    public String getQueryText() {
        return queryText;
    }

    public int getTopK() {
        return topK;
    }

    public Map<String, Double> getBoost() {
        return boost;
    }

    public Integer getTimeBudgetMs() {
        return timeBudgetMs;
    }

    public String getOperator() {
        return operator;
    }

    public String getMinimumShouldMatch() {
        return minimumShouldMatch;
    }

    public List<Map<String, Object>> getFilters() {
        return filters;
    }

    public List<String> getFieldsOverride() {
        return fieldsOverride;
    }

    public Map<String, Object> getQueryOverride() {
        return queryOverride;
    }

    public boolean isDebug() {
        return debug;
    }

    public boolean isExplain() {
        return explain;
    }

    public String getTraceId() {
        return traceId;
    }

    public String getRequestId() {
        return requestId;
    }
}
