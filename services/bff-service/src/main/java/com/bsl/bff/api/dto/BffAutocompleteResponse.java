package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class BffAutocompleteResponse {
    private String version;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    @JsonProperty("took_ms")
    private long tookMs;

    private List<Suggestion> suggestions;

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

    public long getTookMs() {
        return tookMs;
    }

    public void setTookMs(long tookMs) {
        this.tookMs = tookMs;
    }

    public List<Suggestion> getSuggestions() {
        return suggestions;
    }

    public void setSuggestions(List<Suggestion> suggestions) {
        this.suggestions = suggestions;
    }

    public static class Suggestion {
        private String text;
        private double score;
        private String source;

        public String getText() {
            return text;
        }

        public void setText(String text) {
            this.text = text;
        }

        public double getScore() {
            return score;
        }

        public void setScore(double score) {
            this.score = score;
        }

        public String getSource() {
            return source;
        }

        public void setSource(String source) {
            this.source = source;
        }
    }
}
