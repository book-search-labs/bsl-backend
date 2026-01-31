package com.bsl.autocomplete.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class AdminAutocompleteResponse {
    @JsonProperty("took_ms")
    private long tookMs;

    private List<Suggestion> suggestions;

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
        @JsonProperty("suggest_id")
        private String suggestId;
        private String text;
        private String type;
        private String lang;
        @JsonProperty("target_id")
        private String targetId;
        @JsonProperty("target_doc_id")
        private String targetDocId;
        private Integer weight;
        @JsonProperty("ctr_7d")
        private Double ctr7d;
        @JsonProperty("popularity_7d")
        private Double popularity7d;
        @JsonProperty("is_blocked")
        private Boolean blocked;

        public String getSuggestId() {
            return suggestId;
        }

        public void setSuggestId(String suggestId) {
            this.suggestId = suggestId;
        }

        public String getText() {
            return text;
        }

        public void setText(String text) {
            this.text = text;
        }

        public String getType() {
            return type;
        }

        public void setType(String type) {
            this.type = type;
        }

        public String getLang() {
            return lang;
        }

        public void setLang(String lang) {
            this.lang = lang;
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

        public Integer getWeight() {
            return weight;
        }

        public void setWeight(Integer weight) {
            this.weight = weight;
        }

        public Double getCtr7d() {
            return ctr7d;
        }

        public void setCtr7d(Double ctr7d) {
            this.ctr7d = ctr7d;
        }

        public Double getPopularity7d() {
            return popularity7d;
        }

        public void setPopularity7d(Double popularity7d) {
            this.popularity7d = popularity7d;
        }

        public Boolean getBlocked() {
            return blocked;
        }

        public void setBlocked(Boolean blocked) {
            this.blocked = blocked;
        }
    }
}
