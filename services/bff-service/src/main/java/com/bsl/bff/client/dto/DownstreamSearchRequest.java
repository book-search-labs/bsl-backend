package com.bsl.bff.client.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class DownstreamSearchRequest {
    private Query query;
    private Options options;

    @JsonProperty("query_context")
    private JsonNode queryContext;

    @JsonProperty("query_context_v1_1")
    private JsonNode queryContextV11;

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

    public JsonNode getQueryContext() {
        return queryContext;
    }

    public void setQueryContext(JsonNode queryContext) {
        this.queryContext = queryContext;
    }

    public JsonNode getQueryContextV11() {
        return queryContextV11;
    }

    public void setQueryContextV11(JsonNode queryContextV11) {
        this.queryContextV11 = queryContextV11;
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

    public static class Options {
        private Integer size;
        private Integer from;

        @JsonProperty("enableVector")
        private Boolean enableVector;

        private Integer rrfK;
        private Integer timeoutMs;

        public Integer getSize() {
            return size;
        }

        public void setSize(Integer size) {
            this.size = size;
        }

        public Integer getFrom() {
            return from;
        }

        public void setFrom(Integer from) {
            this.from = from;
        }

        public Boolean getEnableVector() {
            return enableVector;
        }

        public void setEnableVector(Boolean enableVector) {
            this.enableVector = enableVector;
        }

        public Integer getRrfK() {
            return rrfK;
        }

        public void setRrfK(Integer rrfK) {
            this.rrfK = rrfK;
        }

        public Integer getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(Integer timeoutMs) {
            this.timeoutMs = timeoutMs;
        }
    }
}
