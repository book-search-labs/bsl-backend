package com.bsl.search.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class SearchRequest {
    private Query query;
    private Options options;

    @JsonProperty("query_context")
    private QueryContext queryContext;

    @JsonProperty("query_context_v1_1")
    private QueryContextV1_1 queryContextV1_1;

    public Query getQuery() {
        return query;
    }

    public void setQuery(Query query) {
        this.query = query;
    }

    public Options getOptions() {
        return options;
    }

    public void setOptions(Options options) {
        this.options = options;
    }

    public QueryContext getQueryContext() {
        return queryContext;
    }

    public void setQueryContext(QueryContext queryContext) {
        this.queryContext = queryContext;
    }

    public QueryContextV1_1 getQueryContextV1_1() {
        return queryContextV1_1;
    }

    public void setQueryContextV1_1(QueryContextV1_1 queryContextV1_1) {
        this.queryContextV1_1 = queryContextV1_1;
    }

    public static class Query {
        private String raw;

        public String getRaw() {
            return raw;
        }

        public void setRaw(String raw) {
            this.raw = raw;
        }
    }
}
