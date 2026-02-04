package com.bsl.ranking.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.databind.JsonNode;
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

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Options {
        private Integer size;
        private Boolean debug;
        private String model;
        private Boolean rerankEnabled;
        private RerankConfig rerankConfig;

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

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        @JsonIgnore
        public Boolean getRerank() {
            return rerankEnabled;
        }

        @JsonIgnore
        public void setRerank(Boolean rerankEnabled) {
            this.rerankEnabled = rerankEnabled;
            this.rerankConfig = null;
        }

        @JsonIgnore
        public RerankConfig getRerankConfig() {
            return rerankConfig;
        }

        @JsonIgnore
        public void setRerankConfig(RerankConfig rerankConfig) {
            this.rerankConfig = rerankConfig;
            if (rerankConfig != null) {
                this.rerankEnabled = rerankConfig.getEnabled() == null ? true : rerankConfig.getEnabled();
            }
        }

        @JsonSetter("rerank")
        public void setRerankNode(JsonNode rerankNode) {
            if (rerankNode == null || rerankNode.isNull()) {
                return;
            }
            if (rerankNode.isBoolean()) {
                this.rerankEnabled = rerankNode.asBoolean();
                this.rerankConfig = null;
                return;
            }
            if (!rerankNode.isObject()) {
                return;
            }
            RerankConfig config = new RerankConfig();
            if (rerankNode.has("enabled") && rerankNode.get("enabled").isBoolean()) {
                config.setEnabled(rerankNode.get("enabled").asBoolean());
                this.rerankEnabled = config.getEnabled();
            } else {
                this.rerankEnabled = true;
            }
            if (rerankNode.has("stage1") && rerankNode.get("stage1").isObject()) {
                config.setStage1(parseStage(rerankNode.get("stage1")));
            }
            if (rerankNode.has("stage2") && rerankNode.get("stage2").isObject()) {
                config.setStage2(parseStage(rerankNode.get("stage2")));
            }
            if (rerankNode.has("model") && rerankNode.get("model").isTextual()) {
                config.setModel(rerankNode.get("model").asText());
            }
            this.rerankConfig = config;
        }

        private StageConfig parseStage(JsonNode stageNode) {
            StageConfig stage = new StageConfig();
            if (stageNode.has("enabled") && stageNode.get("enabled").isBoolean()) {
                stage.setEnabled(stageNode.get("enabled").asBoolean());
            }
            if (stageNode.has("topK") && stageNode.get("topK").canConvertToInt()) {
                stage.setTopK(stageNode.get("topK").asInt());
            }
            if (stageNode.has("model") && stageNode.get("model").isTextual()) {
                stage.setModel(stageNode.get("model").asText());
            }
            return stage;
        }

        public Integer getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(Integer timeoutMs) {
            this.timeoutMs = timeoutMs;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RerankConfig {
        private Boolean enabled;
        private StageConfig stage1;
        private StageConfig stage2;
        private String model;

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public StageConfig getStage1() {
            return stage1;
        }

        public void setStage1(StageConfig stage1) {
            this.stage1 = stage1;
        }

        public StageConfig getStage2() {
            return stage2;
        }

        public void setStage2(StageConfig stage2) {
            this.stage2 = stage2;
        }

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class StageConfig {
        private Boolean enabled;
        private Integer topK;
        private String model;

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        @JsonProperty("topK")
        public Integer getTopK() {
            return topK;
        }

        @JsonProperty("topK")
        public void setTopK(Integer topK) {
            this.topK = topK;
        }

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }
    }

    public static class Candidate {
        @JsonProperty("doc_id")
        private String docId;

        private String doc;
        private String title;
        private List<String> authors;
        private String series;
        private String publisher;

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

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public List<String> getAuthors() {
            return authors;
        }

        public void setAuthors(List<String> authors) {
            this.authors = authors;
        }

        public String getSeries() {
            return series;
        }

        public void setSeries(String series) {
            this.series = series;
        }

        public String getPublisher() {
            return publisher;
        }

        public void setPublisher(String publisher) {
            this.publisher = publisher;
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

        @JsonProperty("fused_rank")
        private Integer fusedRank;

        @JsonProperty("rrf_rank")
        private Integer rrfRank;

        @JsonProperty("bm25_score")
        private Double bm25Score;

        @JsonProperty("vec_score")
        private Double vecScore;

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

        public Integer getFusedRank() {
            return fusedRank;
        }

        public void setFusedRank(Integer fusedRank) {
            this.fusedRank = fusedRank;
        }

        public Integer getRrfRank() {
            return rrfRank;
        }

        public void setRrfRank(Integer rrfRank) {
            this.rrfRank = rrfRank;
        }

        public Double getBm25Score() {
            return bm25Score;
        }

        public void setBm25Score(Double bm25Score) {
            this.bm25Score = bm25Score;
        }

        public Double getVecScore() {
            return vecScore;
        }

        public void setVecScore(Double vecScore) {
            this.vecScore = vecScore;
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
