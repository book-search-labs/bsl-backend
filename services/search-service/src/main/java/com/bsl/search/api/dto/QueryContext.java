package com.bsl.search.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public class QueryContext {
    private String version;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    private Query query;

    @JsonProperty("retrieval_hints")
    private RetrievalHints retrievalHints;

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getTraceId() {
        return traceId;
    }

    public void setTraceId(String traceId) {
        this.traceId = traceId;
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public Query getQuery() {
        return query;
    }

    public void setQuery(Query query) {
        this.query = query;
    }

    public RetrievalHints getRetrievalHints() {
        return retrievalHints;
    }

    public void setRetrievalHints(RetrievalHints retrievalHints) {
        this.retrievalHints = retrievalHints;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Query {
        private String raw;
        private String normalized;
        private String canonical;

        public String getRaw() {
            return raw;
        }

        public void setRaw(String raw) {
            this.raw = raw;
        }

        public String getNormalized() {
            return normalized;
        }

        public void setNormalized(String normalized) {
            this.normalized = normalized;
        }

        public String getCanonical() {
            return canonical;
        }

        public void setCanonical(String canonical) {
            this.canonical = canonical;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RetrievalHints {
        private String strategy;

        @JsonProperty("top_k")
        private Integer topK;

        @JsonProperty("time_budget_ms")
        private Integer timeBudgetMs;

        private Map<String, Double> boost;

        public String getStrategy() {
            return strategy;
        }

        public void setStrategy(String strategy) {
            this.strategy = strategy;
        }

        public Integer getTopK() {
            return topK;
        }

        public void setTopK(Integer topK) {
            this.topK = topK;
        }

        public Integer getTimeBudgetMs() {
            return timeBudgetMs;
        }

        public void setTimeBudgetMs(Integer timeBudgetMs) {
            this.timeBudgetMs = timeBudgetMs;
        }

        public Map<String, Double> getBoost() {
            return boost;
        }

        public void setBoost(Map<String, Double> boost) {
            this.boost = boost;
        }
    }
}
