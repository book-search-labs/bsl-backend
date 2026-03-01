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
    private Integer total;
    private List<BookHit> hits;
    private Debug debug;

    @JsonProperty("experiment_bucket")
    private String experimentBucket;

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

    public Integer getTotal() {
        return total;
    }

    public void setTotal(Integer total) {
        this.total = total;
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

    public String getExperimentBucket() {
        return experimentBucket;
    }

    public void setExperimentBucket(String experimentBucket) {
        this.experimentBucket = experimentBucket;
    }

    public static class Debug {
        @JsonProperty("applied_fallback_id")
        private String appliedFallbackId;

        @JsonProperty("query_text_source_used")
        private String queryTextSourceUsed;

        private Stages stages;

        @JsonProperty("query_dsl")
        private Object queryDsl;

        private Retrieval retrieval;

        private Cache cache;

        private List<String> warnings;

        @JsonProperty("experiment_bucket")
        private String experimentBucket;

        @JsonProperty("experiment_applied")
        private Boolean experimentApplied;

        @JsonProperty("enhance_applied")
        private Boolean enhanceApplied;

        @JsonProperty("enhance_reason")
        private String enhanceReason;

        @JsonProperty("enhance_strategy")
        private String enhanceStrategy;

        @JsonProperty("enhance_final_query")
        private String enhanceFinalQuery;

        @JsonProperty("enhance_final_source")
        private String enhanceFinalSource;

        @JsonProperty("enhance_improved")
        private Boolean enhanceImproved;

        @JsonProperty("enhance_skip_reason")
        private String enhanceSkipReason;

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

        public Object getQueryDsl() {
            return queryDsl;
        }

        public void setQueryDsl(Object queryDsl) {
            this.queryDsl = queryDsl;
        }

        public Retrieval getRetrieval() {
            return retrieval;
        }

        public void setRetrieval(Retrieval retrieval) {
            this.retrieval = retrieval;
        }

        public Cache getCache() {
            return cache;
        }

        public void setCache(Cache cache) {
            this.cache = cache;
        }

        public List<String> getWarnings() {
            return warnings;
        }

        public void setWarnings(List<String> warnings) {
            this.warnings = warnings;
        }

        public String getExperimentBucket() {
            return experimentBucket;
        }

        public void setExperimentBucket(String experimentBucket) {
            this.experimentBucket = experimentBucket;
        }

        public Boolean getExperimentApplied() {
            return experimentApplied;
        }

        public void setExperimentApplied(Boolean experimentApplied) {
            this.experimentApplied = experimentApplied;
        }

        public Boolean getEnhanceApplied() {
            return enhanceApplied;
        }

        public void setEnhanceApplied(Boolean enhanceApplied) {
            this.enhanceApplied = enhanceApplied;
        }

        public String getEnhanceReason() {
            return enhanceReason;
        }

        public void setEnhanceReason(String enhanceReason) {
            this.enhanceReason = enhanceReason;
        }

        public String getEnhanceStrategy() {
            return enhanceStrategy;
        }

        public void setEnhanceStrategy(String enhanceStrategy) {
            this.enhanceStrategy = enhanceStrategy;
        }

        public String getEnhanceFinalQuery() {
            return enhanceFinalQuery;
        }

        public void setEnhanceFinalQuery(String enhanceFinalQuery) {
            this.enhanceFinalQuery = enhanceFinalQuery;
        }

        public String getEnhanceFinalSource() {
            return enhanceFinalSource;
        }

        public void setEnhanceFinalSource(String enhanceFinalSource) {
            this.enhanceFinalSource = enhanceFinalSource;
        }

        public Boolean getEnhanceImproved() {
            return enhanceImproved;
        }

        public void setEnhanceImproved(Boolean enhanceImproved) {
            this.enhanceImproved = enhanceImproved;
        }

        public String getEnhanceSkipReason() {
            return enhanceSkipReason;
        }

        public void setEnhanceSkipReason(String enhanceSkipReason) {
            this.enhanceSkipReason = enhanceSkipReason;
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

    public static class Retrieval {
        private Stage lexical;
        private Stage vector;
        private Stage fusion;
        private Stage rerank;

        public Stage getLexical() {
            return lexical;
        }

        public void setLexical(Stage lexical) {
            this.lexical = lexical;
        }

        public Stage getVector() {
            return vector;
        }

        public void setVector(Stage vector) {
            this.vector = vector;
        }

        public Stage getFusion() {
            return fusion;
        }

        public void setFusion(Stage fusion) {
            this.fusion = fusion;
        }

        public Stage getRerank() {
            return rerank;
        }

        public void setRerank(Stage rerank) {
            this.rerank = rerank;
        }
    }

    public static class Stage {
        @JsonProperty("took_ms")
        private Long tookMs;

        @JsonProperty("doc_count")
        private Integer docCount;

        @JsonProperty("top_k")
        private Integer topK;

        private Boolean error;

        @JsonProperty("timed_out")
        private Boolean timedOut;

        @JsonProperty("error_message")
        private String errorMessage;

        private String mode;

        public Long getTookMs() {
            return tookMs;
        }

        public void setTookMs(Long tookMs) {
            this.tookMs = tookMs;
        }

        public Integer getDocCount() {
            return docCount;
        }

        public void setDocCount(Integer docCount) {
            this.docCount = docCount;
        }

        public Integer getTopK() {
            return topK;
        }

        public void setTopK(Integer topK) {
            this.topK = topK;
        }

        public Boolean getError() {
            return error;
        }

        public void setError(Boolean error) {
            this.error = error;
        }

        public Boolean getTimedOut() {
            return timedOut;
        }

        public void setTimedOut(Boolean timedOut) {
            this.timedOut = timedOut;
        }

        public String getErrorMessage() {
            return errorMessage;
        }

        public void setErrorMessage(String errorMessage) {
            this.errorMessage = errorMessage;
        }

        public String getMode() {
            return mode;
        }

        public void setMode(String mode) {
            this.mode = mode;
        }
    }

    public static class Cache {
        private boolean hit;

        @JsonProperty("age_ms")
        private Long ageMs;

        @JsonProperty("ttl_ms")
        private Long ttlMs;

        private String key;

        public boolean isHit() {
            return hit;
        }

        public void setHit(boolean hit) {
            this.hit = hit;
        }

        public Long getAgeMs() {
            return ageMs;
        }

        public void setAgeMs(Long ageMs) {
            this.ageMs = ageMs;
        }

        public Long getTtlMs() {
            return ttlMs;
        }

        public void setTtlMs(Long ttlMs) {
            this.ttlMs = ttlMs;
        }

        public String getKey() {
            return key;
        }

        public void setKey(String key) {
            this.key = key;
        }
    }
}
