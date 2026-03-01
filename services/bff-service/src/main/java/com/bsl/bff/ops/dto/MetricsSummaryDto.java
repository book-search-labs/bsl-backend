package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class MetricsSummaryDto {
    @JsonProperty("query_count")
    private long queryCount;

    @JsonProperty("p95_ms")
    private double p95Ms;

    @JsonProperty("p99_ms")
    private double p99Ms;

    @JsonProperty("zero_result_rate")
    private double zeroResultRate;

    @JsonProperty("rerank_rate")
    private double rerankRate;

    @JsonProperty("error_rate")
    private double errorRate;

    public long getQueryCount() {
        return queryCount;
    }

    public void setQueryCount(long queryCount) {
        this.queryCount = queryCount;
    }

    public double getP95Ms() {
        return p95Ms;
    }

    public void setP95Ms(double p95Ms) {
        this.p95Ms = p95Ms;
    }

    public double getP99Ms() {
        return p99Ms;
    }

    public void setP99Ms(double p99Ms) {
        this.p99Ms = p99Ms;
    }

    public double getZeroResultRate() {
        return zeroResultRate;
    }

    public void setZeroResultRate(double zeroResultRate) {
        this.zeroResultRate = zeroResultRate;
    }

    public double getRerankRate() {
        return rerankRate;
    }

    public void setRerankRate(double rerankRate) {
        this.rerankRate = rerankRate;
    }

    public double getErrorRate() {
        return errorRate;
    }

    public void setErrorRate(double errorRate) {
        this.errorRate = errorRate;
    }
}
