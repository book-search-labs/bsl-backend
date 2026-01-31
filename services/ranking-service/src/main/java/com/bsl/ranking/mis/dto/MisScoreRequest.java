package com.bsl.ranking.mis.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class MisScoreRequest {
    private String version;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    private String model;
    private String task;
    private List<Pair> pairs;
    private Options options;

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

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public String getTask() {
        return task;
    }

    public void setTask(String task) {
        this.task = task;
    }

    public List<Pair> getPairs() {
        return pairs;
    }

    public void setPairs(List<Pair> pairs) {
        this.pairs = pairs;
    }

    public Options getOptions() {
        return options;
    }

    public void setOptions(Options options) {
        this.options = options;
    }

    public static class Pair {
        @JsonProperty("pair_id")
        private String pairId;
        private String query;
        private String doc;

        @JsonProperty("doc_id")
        private String docId;

        private Features features;

        public String getPairId() {
            return pairId;
        }

        public void setPairId(String pairId) {
            this.pairId = pairId;
        }

        public String getQuery() {
            return query;
        }

        public void setQuery(String query) {
            this.query = query;
        }

        public String getDoc() {
            return doc;
        }

        public void setDoc(String doc) {
            this.doc = doc;
        }

        public String getDocId() {
            return docId;
        }

        public void setDocId(String docId) {
            this.docId = docId;
        }

        public Features getFeatures() {
            return features;
        }

        public void setFeatures(Features features) {
            this.features = features;
        }
    }

    public static class Features {
        @JsonProperty("lex_rank")
        private Integer lexRank;

        @JsonProperty("vec_rank")
        private Integer vecRank;

        @JsonProperty("rrf_score")
        private Double rrfScore;

        @JsonProperty("issued_year")
        private Integer issuedYear;

        private Integer volume;

        @JsonProperty("edition_labels")
        private List<String> editionLabels;

        public Integer getLexRank() {
            return lexRank;
        }

        public void setLexRank(Integer lexRank) {
            this.lexRank = lexRank;
        }

        public Integer getVecRank() {
            return vecRank;
        }

        public void setVecRank(Integer vecRank) {
            this.vecRank = vecRank;
        }

        public Double getRrfScore() {
            return rrfScore;
        }

        public void setRrfScore(Double rrfScore) {
            this.rrfScore = rrfScore;
        }

        public Integer getIssuedYear() {
            return issuedYear;
        }

        public void setIssuedYear(Integer issuedYear) {
            this.issuedYear = issuedYear;
        }

        public Integer getVolume() {
            return volume;
        }

        public void setVolume(Integer volume) {
            this.volume = volume;
        }

        public List<String> getEditionLabels() {
            return editionLabels;
        }

        public void setEditionLabels(List<String> editionLabels) {
            this.editionLabels = editionLabels;
        }
    }

    public static class Options {
        @JsonProperty("timeout_ms")
        private Integer timeoutMs;

        @JsonProperty("return_debug")
        private Boolean returnDebug;

        public Integer getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(Integer timeoutMs) {
            this.timeoutMs = timeoutMs;
        }

        public Boolean getReturnDebug() {
            return returnDebug;
        }

        public void setReturnDebug(Boolean returnDebug) {
            this.returnDebug = returnDebug;
        }
    }
}
