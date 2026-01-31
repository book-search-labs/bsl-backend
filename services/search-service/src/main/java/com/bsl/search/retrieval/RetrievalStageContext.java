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
    private final boolean debug;
    private final boolean explain;

    public RetrievalStageContext(
        String queryText,
        int topK,
        Map<String, Double> boost,
        Integer timeBudgetMs,
        String operator,
        String minimumShouldMatch,
        List<Map<String, Object>> filters,
        List<String> fieldsOverride,
        boolean debug,
        boolean explain
    ) {
        this.queryText = queryText;
        this.topK = topK;
        this.boost = boost == null ? Collections.emptyMap() : boost;
        this.timeBudgetMs = timeBudgetMs;
        this.operator = operator;
        this.minimumShouldMatch = minimumShouldMatch;
        this.filters = filters == null ? List.of() : filters;
        this.fieldsOverride = fieldsOverride;
        this.debug = debug;
        this.explain = explain;
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

    public boolean isDebug() {
        return debug;
    }

    public boolean isExplain() {
        return explain;
    }
}
