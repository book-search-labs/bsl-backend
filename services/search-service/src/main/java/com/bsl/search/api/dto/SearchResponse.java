package com.bsl.search.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class SearchResponse {
    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    @JsonProperty("took_ms")
    private long tookMs;

    @JsonProperty("ranking_applied")
    private boolean rankingApplied;

    private String strategy;
    private List<BookHit> hits;
    private Debug debug;

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

    public long getTookMs() {
        return tookMs;
    }

    public void setTookMs(long tookMs) {
        this.tookMs = tookMs;
    }

    public boolean isRankingApplied() {
        return rankingApplied;
    }

    public void setRankingApplied(boolean rankingApplied) {
        this.rankingApplied = rankingApplied;
    }

    public String getStrategy() {
        return strategy;
    }

    public void setStrategy(String strategy) {
        this.strategy = strategy;
    }

    public List<BookHit> getHits() {
        return hits;
    }

    public void setHits(List<BookHit> hits) {
        this.hits = hits;
    }

    public Debug getDebug() {
        return debug;
    }

    public void setDebug(Debug debug) {
        this.debug = debug;
    }

    public static class Debug {
        @JsonProperty("applied_fallback_id")
        private String appliedFallbackId;

        @JsonProperty("query_text_source_used")
        private String queryTextSourceUsed;

        private Stages stages;

        public String getAppliedFallbackId() {
            return appliedFallbackId;
        }

        public void setAppliedFallbackId(String appliedFallbackId) {
            this.appliedFallbackId = appliedFallbackId;
        }

        public String getQueryTextSourceUsed() {
            return queryTextSourceUsed;
        }

        public void setQueryTextSourceUsed(String queryTextSourceUsed) {
            this.queryTextSourceUsed = queryTextSourceUsed;
        }

        public Stages getStages() {
            return stages;
        }

        public void setStages(Stages stages) {
            this.stages = stages;
        }
    }

    public static class Stages {
        private boolean lexical;
        private boolean vector;
        private boolean rerank;

        public boolean isLexical() {
            return lexical;
        }

        public void setLexical(boolean lexical) {
            this.lexical = lexical;
        }

        public boolean isVector() {
            return vector;
        }

        public void setVector(boolean vector) {
            this.vector = vector;
        }

        public boolean isRerank() {
            return rerank;
        }

        public void setRerank(boolean rerank) {
            this.rerank = rerank;
        }
    }
}
