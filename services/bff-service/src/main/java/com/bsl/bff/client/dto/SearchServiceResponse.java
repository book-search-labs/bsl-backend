package com.bsl.bff.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class SearchServiceResponse {
    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    @JsonProperty("took_ms")
    private long tookMs;

    @JsonProperty("ranking_applied")
    private boolean rankingApplied;

    private String strategy;
    private List<BookHit> hits;

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

    public boolean isRankingApplied() {
        return rankingApplied;
    }

    public void setRankingApplied(boolean rankingApplied) {
        this.rankingApplied = rankingApplied;
    }

    public String getStrategy() {
        return strategy;
    }

    public void setStrategy(String strategy) {
        this.strategy = strategy;
    }

    public List<BookHit> getHits() {
        return hits;
    }

    public void setHits(List<BookHit> hits) {
        this.hits = hits;
    }

    public static class BookHit {
        @JsonProperty("doc_id")
        private String docId;
        private double score;
        private Source source;

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

        public Source getSource() {
            return source;
        }

        public void setSource(Source source) {
            this.source = source;
        }
    }

    public static class Source {
        @JsonProperty("title_ko")
        private String titleKo;

        private List<String> authors;

        @JsonProperty("publisher_name")
        private String publisherName;

        @JsonProperty("issued_year")
        private Integer issuedYear;

        public String getTitleKo() {
            return titleKo;
        }

        public void setTitleKo(String titleKo) {
            this.titleKo = titleKo;
        }

        public List<String> getAuthors() {
            return authors;
        }

        public void setAuthors(List<String> authors) {
            this.authors = authors;
        }

        public String getPublisherName() {
            return publisherName;
        }

        public void setPublisherName(String publisherName) {
            this.publisherName = publisherName;
        }

        public Integer getIssuedYear() {
            return issuedYear;
        }

        public void setIssuedYear(Integer issuedYear) {
            this.issuedYear = issuedYear;
        }
    }
}
