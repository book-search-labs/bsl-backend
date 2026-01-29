package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

@JsonIgnoreProperties(ignoreUnknown = true)
public class BffSearchRequest {
    private Query query;

    @JsonProperty("query_context")
    private JsonNode queryContext;

    @JsonProperty("query_context_v1_1")
    private JsonNode queryContextV11;

    private Pagination pagination;
    private Options options;

    public Query getQuery() {
        return query;
    }

    public void setQuery(Query query) {
        this.query = query;
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

    public Pagination getPagination() {
        return pagination;
    }

    public void setPagination(Pagination pagination) {
        this.pagination = pagination;
    }

    public Options getOptions() {
        return options;
    }

    public void setOptions(Options options) {
        this.options = options;
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

    public static class Pagination {
        private Integer from;
        private Integer size;

        public Integer getFrom() {
            return from;
        }

        public void setFrom(Integer from) {
            this.from = from;
        }

        public Integer getSize() {
            return size;
        }

        public void setSize(Integer size) {
            this.size = size;
        }
    }

    public static class Options {
        private Integer from;
        private Integer size;

        @JsonProperty("enable_vector")
        @com.fasterxml.jackson.annotation.JsonAlias("enableVector")
        private Boolean enableVector;

        @JsonProperty("rrf_k")
        @com.fasterxml.jackson.annotation.JsonAlias("rrfK")
        private Integer rrfK;

        public Integer getFrom() {
            return from;
        }

        public void setFrom(Integer from) {
            this.from = from;
        }

        public Integer getSize() {
            return size;
        }

        public void setSize(Integer size) {
            this.size = size;
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
    }
}
