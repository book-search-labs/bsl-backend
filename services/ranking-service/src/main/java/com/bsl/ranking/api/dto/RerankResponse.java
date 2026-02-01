package com.bsl.ranking.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

public class RerankResponse {
    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    @JsonProperty("took_ms")
    private long tookMs;

    private String model;
    private List<Hit> hits;
    private DebugInfo debug;

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

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public List<Hit> getHits() {
        return hits;
    }

    public void setHits(List<Hit> hits) {
        this.hits = hits;
    }

    public DebugInfo getDebug() {
        return debug;
    }

    public void setDebug(DebugInfo debug) {
        this.debug = debug;
    }

    public static class Hit {
        @JsonProperty("doc_id")
        private String docId;

        private double score;
        private int rank;
        private Debug debug;

        public String getDocId() {
            return docId;
        }

        public void setDocId(String docId) {
            this.docId = docId;
        }

        public double getScore() {
            return score;
        }

        public void setScore(double score) {
            this.score = score;
        }

        public int getRank() {
            return rank;
        }

        public void setRank(int rank) {
            this.rank = rank;
        }

        public Debug getDebug() {
            return debug;
        }

        public void setDebug(Debug debug) {
            this.debug = debug;
        }
    }

    public static class Debug {
        @JsonProperty("lex_rank")
        private Integer lexRank;

        @JsonProperty("vec_rank")
        private Integer vecRank;

        @JsonProperty("base_rrf")
        private double base;

        @JsonProperty("lex_bonus")
        private double lexBonus;

        @JsonProperty("vec_bonus")
        private double vecBonus;

        @JsonProperty("freshness_bonus")
        private double freshnessBonus;

        @JsonProperty("slot_bonus")
        private double slotBonus;

        @JsonProperty("ctr_bonus")
        private Double ctrBonus;

        @JsonProperty("popularity_bonus")
        private Double popularityBonus;

        @JsonProperty("raw_features")
        private Map<String, Object> rawFeatures;

        private Map<String, Double> features;

        @JsonProperty("reason_codes")
        private List<String> reasonCodes;

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

        public double getBase() {
            return base;
        }

        public void setBase(double base) {
            this.base = base;
        }

        public double getLexBonus() {
            return lexBonus;
        }

        public void setLexBonus(double lexBonus) {
            this.lexBonus = lexBonus;
        }

        public double getVecBonus() {
            return vecBonus;
        }

        public void setVecBonus(double vecBonus) {
            this.vecBonus = vecBonus;
        }

        public double getFreshnessBonus() {
            return freshnessBonus;
        }

        public void setFreshnessBonus(double freshnessBonus) {
            this.freshnessBonus = freshnessBonus;
        }

        public double getSlotBonus() {
            return slotBonus;
        }

        public void setSlotBonus(double slotBonus) {
            this.slotBonus = slotBonus;
        }

        public Double getCtrBonus() {
            return ctrBonus;
        }

        public void setCtrBonus(Double ctrBonus) {
            this.ctrBonus = ctrBonus;
        }

        public Double getPopularityBonus() {
            return popularityBonus;
        }

        public void setPopularityBonus(Double popularityBonus) {
            this.popularityBonus = popularityBonus;
        }

        public Map<String, Object> getRawFeatures() {
            return rawFeatures;
        }

        public void setRawFeatures(Map<String, Object> rawFeatures) {
            this.rawFeatures = rawFeatures;
        }

        public Map<String, Double> getFeatures() {
            return features;
        }

        public void setFeatures(Map<String, Double> features) {
            this.features = features;
        }

        public List<String> getReasonCodes() {
            return reasonCodes;
        }

        public void setReasonCodes(List<String> reasonCodes) {
            this.reasonCodes = reasonCodes;
        }
    }

    public static class DebugInfo {
        @JsonProperty("model_id")
        private String modelId;

        @JsonProperty("feature_set_version")
        private String featureSetVersion;

        @JsonProperty("candidates_in")
        private Integer candidatesIn;

        @JsonProperty("candidates_used")
        private Integer candidatesUsed;

        @JsonProperty("timeout_ms")
        private Integer timeoutMs;

        @JsonProperty("rerank_applied")
        private Boolean rerankApplied;

        @JsonProperty("reason_codes")
        private List<String> reasonCodes;

        private Map<String, Object> replay;

        public String getModelId() {
            return modelId;
        }

        public void setModelId(String modelId) {
            this.modelId = modelId;
        }

        public String getFeatureSetVersion() {
            return featureSetVersion;
        }

        public void setFeatureSetVersion(String featureSetVersion) {
            this.featureSetVersion = featureSetVersion;
        }

        public Integer getCandidatesIn() {
            return candidatesIn;
        }

        public void setCandidatesIn(Integer candidatesIn) {
            this.candidatesIn = candidatesIn;
        }

        public Integer getCandidatesUsed() {
            return candidatesUsed;
        }

        public void setCandidatesUsed(Integer candidatesUsed) {
            this.candidatesUsed = candidatesUsed;
        }

        public Integer getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(Integer timeoutMs) {
            this.timeoutMs = timeoutMs;
        }

        public Boolean getRerankApplied() {
            return rerankApplied;
        }

        public void setRerankApplied(Boolean rerankApplied) {
            this.rerankApplied = rerankApplied;
        }

        public List<String> getReasonCodes() {
            return reasonCodes;
        }

        public void setReasonCodes(List<String> reasonCodes) {
            this.reasonCodes = reasonCodes;
        }

        public Map<String, Object> getReplay() {
            return replay;
        }

        public void setReplay(Map<String, Object> replay) {
            this.replay = replay;
        }
    }
}
