package com.bsl.search.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class QueryContextV1_1 {
    private Meta meta;
    private Query query;

    @JsonProperty("retrievalHints")
    private RetrievalHints retrievalHints;

    public Meta getMeta() {
        return meta;
    }

    public void setMeta(Meta meta) {
        this.meta = meta;
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
    public static class Meta {
        private String schemaVersion;
        private String traceId;
        private String requestId;

        public String getSchemaVersion() {
            return schemaVersion;
        }

        public void setSchemaVersion(String schemaVersion) {
            this.schemaVersion = schemaVersion;
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
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Query {
        private String raw;
        private String norm;
        private String finall;

        @JsonProperty("final")
        public String getFinalValue() {
            return finall;
        }

        @JsonProperty("final")
        public void setFinalValue(String finall) {
            this.finall = finall;
        }

        public String getRaw() {
            return raw;
        }

        public void setRaw(String raw) {
            this.raw = raw;
        }

        public String getNorm() {
            return norm;
        }

        public void setNorm(String norm) {
            this.norm = norm;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RetrievalHints {
        private String queryTextSource;
        private Lexical lexical;
        private Vector vector;
        private Rerank rerank;
        private List<Filter> filters;
        private List<FallbackPolicy> fallbackPolicy;
        private ExecutionHint executionHint;

        public String getQueryTextSource() {
            return queryTextSource;
        }

        public void setQueryTextSource(String queryTextSource) {
            this.queryTextSource = queryTextSource;
        }

        public Lexical getLexical() {
            return lexical;
        }

        public void setLexical(Lexical lexical) {
            this.lexical = lexical;
        }

        public Vector getVector() {
            return vector;
        }

        public void setVector(Vector vector) {
            this.vector = vector;
        }

        public Rerank getRerank() {
            return rerank;
        }

        public void setRerank(Rerank rerank) {
            this.rerank = rerank;
        }

        public List<Filter> getFilters() {
            return filters;
        }

        public void setFilters(List<Filter> filters) {
            this.filters = filters;
        }

        public List<FallbackPolicy> getFallbackPolicy() {
            return fallbackPolicy;
        }

        public void setFallbackPolicy(List<FallbackPolicy> fallbackPolicy) {
            this.fallbackPolicy = fallbackPolicy;
        }

        public ExecutionHint getExecutionHint() {
            return executionHint;
        }

        public void setExecutionHint(ExecutionHint executionHint) {
            this.executionHint = executionHint;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Lexical {
        private Boolean enabled;
        private Integer topKHint;
        private String operator;
        private String minimumShouldMatch;
        private List<String> preferredLogicalFields;

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public Integer getTopKHint() {
            return topKHint;
        }

        public void setTopKHint(Integer topKHint) {
            this.topKHint = topKHint;
        }

        public String getOperator() {
            return operator;
        }

        public void setOperator(String operator) {
            this.operator = operator;
        }

        public String getMinimumShouldMatch() {
            return minimumShouldMatch;
        }

        public void setMinimumShouldMatch(String minimumShouldMatch) {
            this.minimumShouldMatch = minimumShouldMatch;
        }

        public List<String> getPreferredLogicalFields() {
            return preferredLogicalFields;
        }

        public void setPreferredLogicalFields(List<String> preferredLogicalFields) {
            this.preferredLogicalFields = preferredLogicalFields;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Vector {
        private Boolean enabled;
        private Integer topKHint;
        private FusionHint fusionHint;

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public Integer getTopKHint() {
            return topKHint;
        }

        public void setTopKHint(Integer topKHint) {
            this.topKHint = topKHint;
        }

        public FusionHint getFusionHint() {
            return fusionHint;
        }

        public void setFusionHint(FusionHint fusionHint) {
            this.fusionHint = fusionHint;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class FusionHint {
        private String method;
        private Integer k;

        public String getMethod() {
            return method;
        }

        public void setMethod(String method) {
            this.method = method;
        }

        public Integer getK() {
            return k;
        }

        public void setK(Integer k) {
            this.k = k;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Rerank {
        private Boolean enabled;
        private Integer topKHint;

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public Integer getTopKHint() {
            return topKHint;
        }

        public void setTopKHint(Integer topKHint) {
            this.topKHint = topKHint;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Filter {
        @JsonProperty("and")
        private List<Constraint> and;

        public List<Constraint> getAnd() {
            return and;
        }

        public void setAnd(List<Constraint> and) {
            this.and = and;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Constraint {
        private String scope;
        private String logicalField;
        private String op;
        private Object value;
        private Boolean strict;
        private String reason;

        public String getScope() {
            return scope;
        }

        public void setScope(String scope) {
            this.scope = scope;
        }

        public String getLogicalField() {
            return logicalField;
        }

        public void setLogicalField(String logicalField) {
            this.logicalField = logicalField;
        }

        public String getOp() {
            return op;
        }

        public void setOp(String op) {
            this.op = op;
        }

        public Object getValue() {
            return value;
        }

        public void setValue(Object value) {
            this.value = value;
        }

        public Boolean getStrict() {
            return strict;
        }

        public void setStrict(Boolean strict) {
            this.strict = strict;
        }

        public String getReason() {
            return reason;
        }

        public void setReason(String reason) {
            this.reason = reason;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class FallbackPolicy {
        private String id;
        private When when;
        private Mutations mutations;

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public When getWhen() {
            return when;
        }

        public void setWhen(When when) {
            this.when = when;
        }

        public Mutations getMutations() {
            return mutations;
        }

        public void setMutations(Mutations mutations) {
            this.mutations = mutations;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class When {
        private Boolean onTimeout;
        private Boolean onVectorError;
        private Boolean onRerankTimeout;
        private Boolean onRerankError;
        private Boolean onZeroResults;

        public Boolean getOnTimeout() {
            return onTimeout;
        }

        public void setOnTimeout(Boolean onTimeout) {
            this.onTimeout = onTimeout;
        }

        public Boolean getOnVectorError() {
            return onVectorError;
        }

        public void setOnVectorError(Boolean onVectorError) {
            this.onVectorError = onVectorError;
        }

        public Boolean getOnRerankTimeout() {
            return onRerankTimeout;
        }

        public void setOnRerankTimeout(Boolean onRerankTimeout) {
            this.onRerankTimeout = onRerankTimeout;
        }

        public Boolean getOnRerankError() {
            return onRerankError;
        }

        public void setOnRerankError(Boolean onRerankError) {
            this.onRerankError = onRerankError;
        }

        public Boolean getOnZeroResults() {
            return onZeroResults;
        }

        public void setOnZeroResults(Boolean onZeroResults) {
            this.onZeroResults = onZeroResults;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Mutations {
        private List<String> disable;
        private String useQueryTextSource;
        private AdjustHint adjustHint;

        public List<String> getDisable() {
            return disable;
        }

        public void setDisable(List<String> disable) {
            this.disable = disable;
        }

        public String getUseQueryTextSource() {
            return useQueryTextSource;
        }

        public void setUseQueryTextSource(String useQueryTextSource) {
            this.useQueryTextSource = useQueryTextSource;
        }

        public AdjustHint getAdjustHint() {
            return adjustHint;
        }

        public void setAdjustHint(AdjustHint adjustHint) {
            this.adjustHint = adjustHint;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class AdjustHint {
        private AdjustLexical lexical;

        public AdjustLexical getLexical() {
            return lexical;
        }

        public void setLexical(AdjustLexical lexical) {
            this.lexical = lexical;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class AdjustLexical {
        private Integer topK;

        public Integer getTopK() {
            return topK;
        }

        public void setTopK(Integer topK) {
            this.topK = topK;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class ExecutionHint {
        private Integer timeoutMs;
        private BudgetMs budgetMs;

        public Integer getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(Integer timeoutMs) {
            this.timeoutMs = timeoutMs;
        }

        public BudgetMs getBudgetMs() {
            return budgetMs;
        }

        public void setBudgetMs(BudgetMs budgetMs) {
            this.budgetMs = budgetMs;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class BudgetMs {
        private Integer lexical;
        private Integer vector;
        private Integer rerank;
        private Integer overhead;

        public Integer getLexical() {
            return lexical;
        }

        public void setLexical(Integer lexical) {
            this.lexical = lexical;
        }

        public Integer getVector() {
            return vector;
        }

        public void setVector(Integer vector) {
            this.vector = vector;
        }

        public Integer getRerank() {
            return rerank;
        }

        public void setRerank(Integer rerank) {
            this.rerank = rerank;
        }

        public Integer getOverhead() {
            return overhead;
        }

        public void setOverhead(Integer overhead) {
            this.overhead = overhead;
        }
    }
}
