package com.bsl.autocomplete.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class AutocompleteResponse {
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
        @JsonProperty("suggest_id")
        private String suggestId;
        private String type;
        @JsonProperty("target_id")
        private String targetId;
        @JsonProperty("target_doc_id")
        private String targetDocId;

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

        public String getSuggestId() {
            return suggestId;
        }

        public void setSuggestId(String suggestId) {
            this.suggestId = suggestId;
        }

        public String getType() {
            return type;
        }

        public void setType(String type) {
            this.type = type;
        }

        public String getTargetId() {
            return targetId;
        }

        public void setTargetId(String targetId) {
            this.targetId = targetId;
        }

        public String getTargetDocId() {
            return targetDocId;
        }

        public void setTargetDocId(String targetDocId) {
            this.targetDocId = targetDocId;
        }
    }
}
