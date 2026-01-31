package com.bsl.search.service;

import com.bsl.search.api.dto.BookDetailResponse;

public class BookDetailResult {
    private final BookDetailResponse response;
    private final String etag;
    private final boolean cacheHit;
    private final long cacheAgeMs;
    private final long cacheTtlMs;
    private final int cacheControlMaxAgeSeconds;

    public BookDetailResult(
        BookDetailResponse response,
        String etag,
        boolean cacheHit,
        long cacheAgeMs,
        long cacheTtlMs,
        int cacheControlMaxAgeSeconds
    ) {
        this.response = response;
        this.etag = etag;
        this.cacheHit = cacheHit;
        this.cacheAgeMs = cacheAgeMs;
        this.cacheTtlMs = cacheTtlMs;
        this.cacheControlMaxAgeSeconds = cacheControlMaxAgeSeconds;
    }

    public BookDetailResponse getResponse() {
        return response;
    }

    public String getEtag() {
        return etag;
    }

    public boolean isCacheHit() {
        return cacheHit;
    }

    public long getCacheAgeMs() {
        return cacheAgeMs;
    }

    public long getCacheTtlMs() {
        return cacheTtlMs;
    }

    public int getCacheControlMaxAgeSeconds() {
        return cacheControlMaxAgeSeconds;
    }
}
