package com.bsl.search.opensearch;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "opensearch")
public class OpenSearchProperties {
    private String baseUrl;
    private String docIndex;
    private String vecIndex;
    private String chunkIndex;
    private int connectTimeoutMs = 200;
    private int readTimeoutMs = 200;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getDocIndex() {
        return docIndex;
    }

    public void setDocIndex(String docIndex) {
        this.docIndex = docIndex;
    }

    public String getVecIndex() {
        return vecIndex;
    }

    public void setVecIndex(String vecIndex) {
        this.vecIndex = vecIndex;
    }

    public String getChunkIndex() {
        return chunkIndex;
    }

    public void setChunkIndex(String chunkIndex) {
        this.chunkIndex = chunkIndex;
    }

    public int getConnectTimeoutMs() {
        return connectTimeoutMs;
    }

    public void setConnectTimeoutMs(int connectTimeoutMs) {
        this.connectTimeoutMs = connectTimeoutMs;
    }

    public int getReadTimeoutMs() {
        return readTimeoutMs;
    }

    public void setReadTimeoutMs(int readTimeoutMs) {
        this.readTimeoutMs = readTimeoutMs;
    }
}
