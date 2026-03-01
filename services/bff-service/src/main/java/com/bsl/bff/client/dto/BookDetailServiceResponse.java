package com.bsl.bff.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class BookDetailServiceResponse {
    @JsonProperty("doc_id")
    private String docId;

    private Source source;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    @JsonProperty("took_ms")
    private long tookMs;

    public String getDocId() {
        return docId;
    }

    public void setDocId(String docId) {
        this.docId = docId;
    }

    public Source getSource() {
        return source;
    }

    public void setSource(Source source) {
        this.source = source;
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

    public long getTookMs() {
        return tookMs;
    }

    public void setTookMs(long tookMs) {
        this.tookMs = tookMs;
    }

    public static class Source {
        @JsonProperty("title_ko")
        private String titleKo;

        private List<String> authors;

        @JsonProperty("publisher_name")
        private String publisherName;

        @JsonProperty("issued_year")
        private Integer issuedYear;

        private Integer volume;

        @JsonProperty("edition_labels")
        private List<String> editionLabels;

        @JsonProperty("kdc_code")
        private String kdcCode;

        @JsonProperty("kdc_path_codes")
        private List<String> kdcPathCodes;

        @JsonProperty("isbn13")
        private String isbn13;

        @JsonProperty("cover_url")
        private String coverUrl;

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

        public String getKdcCode() {
            return kdcCode;
        }

        public void setKdcCode(String kdcCode) {
            this.kdcCode = kdcCode;
        }

        public List<String> getKdcPathCodes() {
            return kdcPathCodes;
        }

        public void setKdcPathCodes(List<String> kdcPathCodes) {
            this.kdcPathCodes = kdcPathCodes;
        }

        public String getIsbn13() {
            return isbn13;
        }

        public void setIsbn13(String isbn13) {
            this.isbn13 = isbn13;
        }

        public String getCoverUrl() {
            return coverUrl;
        }

        public void setCoverUrl(String coverUrl) {
            this.coverUrl = coverUrl;
        }
    }
}
