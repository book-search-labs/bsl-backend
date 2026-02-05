package com.bsl.search.cache;

import com.bsl.search.api.dto.BookDetailResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookDetailCacheService {
    private final BookCacheProperties properties;
    private final ObjectMapper objectMapper;
    private final TtlCache<BookDetailResponse> cache;

    public BookDetailCacheService(BookCacheProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.cache = new TtlCache<>(properties.getMaxEntries());
    }

    public boolean isEnabled() {
        return properties.isEnabled();
    }

    public Optional<CachedBook> get(String docId) {
        if (!properties.isEnabled() || docId == null || docId.isBlank()) {
            return Optional.empty();
        }
        String key = keyFor(docId);
        return cache.get(key).map(entry -> {
            String etag = computeEtag(entry.getValue());
            return new CachedBook(entry.getValue(), etag, entry.getCreatedAt(), entry.getExpiresAt());
        });
    }

    public void put(String docId, BookDetailResponse response) {
        if (!properties.isEnabled() || docId == null || docId.isBlank() || response == null) {
            return;
        }
        cache.put(keyFor(docId), response, properties.getTtlMs());
    }

    public int getCacheControlMaxAgeSeconds() {
        return properties.getCacheControlMaxAgeSeconds();
    }

    public long getTtlMs() {
        return properties.getTtlMs();
    }

    public String keyFor(String docId) {
        String prefix = properties.getKeyPrefix();
        return (prefix == null ? "" : prefix) + docId;
    }

    public String computeEtag(BookDetailResponse response) {
        if (response == null || response.getSource() == null) {
            return null;
        }
        try {
            String json = objectMapper.writeValueAsString(response.getSource());
            return CacheKeyUtil.sha256(json);
        } catch (JsonProcessingException e) {
            return null;
        }
    }

    public static class CachedBook {
        private final BookDetailResponse response;
        private final String etag;
        private final long createdAt;
        private final long expiresAt;

        public CachedBook(BookDetailResponse response, String etag, long createdAt, long expiresAt) {
            this.response = response;
            this.etag = etag;
            this.createdAt = createdAt;
            this.expiresAt = expiresAt;
        }

        public BookDetailResponse getResponse() {
            return response;
        }

        public String getEtag() {
            return etag;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public long getExpiresAt() {
            return expiresAt;
        }
    }
}
