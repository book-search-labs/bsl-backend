package com.bsl.search.ranking.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class RerankResponse {
    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    @JsonProperty("took_ms")
    private long tookMs;

    private String model;
    private List<Hit> hits;

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

    @JsonIgnoreProperties(ignoreUnknown = true)
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

    @JsonIgnoreProperties(ignoreUnknown = true)
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
    }
}
