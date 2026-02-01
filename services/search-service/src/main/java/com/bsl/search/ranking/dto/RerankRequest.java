package com.bsl.search.ranking.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class RerankRequest {
    private Query query;
    private List<Candidate> candidates;
    private Options options;

    public Query getQuery() {
        return query;
    }

    public void setQuery(Query query) {
        this.query = query;
    }

    public List<Candidate> getCandidates() {
        return candidates;
    }

    public void setCandidates(List<Candidate> candidates) {
        this.candidates = candidates;
    }

    public Options getOptions() {
        return options;
    }

    public void setOptions(Options options) {
        this.options = options;
    }

    public static class Query {
        private String text;

        public String getText() {
            return text;
        }

        public void setText(String text) {
            this.text = text;
        }
    }

    public static class Options {
        private Integer size;
        private Boolean debug;

        @JsonProperty("timeout_ms")
        private Integer timeoutMs;

        public Integer getSize() {
            return size;
        }

        public void setSize(Integer size) {
            this.size = size;
        }

        public Boolean getDebug() {
            return debug;
        }

        public void setDebug(Boolean debug) {
            this.debug = debug;
        }

        public Integer getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(Integer timeoutMs) {
            this.timeoutMs = timeoutMs;
        }
    }

    public static class Candidate {
        @JsonProperty("doc_id")
        private String docId;

        private String doc;

        private Features features;

        public String getDocId() {
            return docId;
        }

        public void setDocId(String docId) {
            this.docId = docId;
        }

        public String getDoc() {
            return doc;
        }

        public void setDoc(String doc) {
            this.doc = doc;
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
}
