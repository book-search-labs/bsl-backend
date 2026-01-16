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
}
