package com.bsl.search.query.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class QueryEnhanceResponse {
    private String decision;
    private String strategy;

    @JsonProperty("reason_codes")
    private List<String> reasonCodes;

    @JsonProperty("final")
    private FinalQuery finalQuery;

    public String getDecision() {
        return decision;
    }

    public void setDecision(String decision) {
        this.decision = decision;
    }

    public String getStrategy() {
        return strategy;
    }

    public void setStrategy(String strategy) {
        this.strategy = strategy;
    }

    public List<String> getReasonCodes() {
        return reasonCodes;
    }

    public void setReasonCodes(List<String> reasonCodes) {
        this.reasonCodes = reasonCodes;
    }

    public FinalQuery getFinalQuery() {
        return finalQuery;
    }

    public void setFinalQuery(FinalQuery finalQuery) {
        this.finalQuery = finalQuery;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class FinalQuery {
        private String text;
        private String source;

        public String getText() {
            return text;
        }

        public void setText(String text) {
            this.text = text;
        }

        public String getSource() {
            return source;
        }

        public void setSource(String source) {
            this.source = source;
        }
    }
}
