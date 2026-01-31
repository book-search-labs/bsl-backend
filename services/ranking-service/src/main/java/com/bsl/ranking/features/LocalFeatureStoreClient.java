package com.bsl.ranking.features;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class LocalFeatureStoreClient implements FeatureStoreClient {
    private static final Logger log = LoggerFactory.getLogger(LocalFeatureStoreClient.class);
    private final FeatureStoreProperties properties;
    private final ObjectMapper objectMapper;
    private volatile Map<String, Map<String, Object>> cache = Collections.emptyMap();
    private volatile long lastLoadedAt = 0L;
    private volatile long lastModified = 0L;

    public LocalFeatureStoreClient(FeatureStoreProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    public Map<String, Map<String, Object>> fetch(List<String> docIds) {
        maybeReload();
        if (docIds == null || docIds.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<String, Map<String, Object>> result = new HashMap<>();
        for (String docId : docIds) {
            Map<String, Object> entry = cache.get(docId);
            if (entry != null) {
                result.put(docId, entry);
            }
        }
        return result;
    }

    private void maybeReload() {
        long now = Instant.now().toEpochMilli();
        if (now - lastLoadedAt < properties.getRefreshMs()) {
            return;
        }
        Path path = resolvePath(properties.getPath());
        if (!Files.exists(path)) {
            cache = Collections.emptyMap();
            lastLoadedAt = now;
            return;
        }
        try {
            long modified = Files.getLastModifiedTime(path).toMillis();
            if (modified == lastModified && !cache.isEmpty()) {
                lastLoadedAt = now;
                return;
            }
            byte[] content = Files.readAllBytes(path);
            Map<String, Map<String, Object>> data = objectMapper.readValue(
                content,
                new TypeReference<>() {}
            );
            cache = data == null ? Collections.emptyMap() : data;
            lastModified = modified;
            lastLoadedAt = now;
        } catch (IOException ex) {
            log.warn("feature store load failed", ex);
            cache = Collections.emptyMap();
            lastLoadedAt = now;
        }
    }

    private Path resolvePath(String path) {
        Path direct = Path.of(path);
        if (Files.exists(direct) || direct.isAbsolute()) {
            return direct;
        }
        Path candidate = direct;
        for (int i = 0; i < 4; i++) {
            if (Files.exists(candidate)) {
                return candidate;
            }
            candidate = Path.of("..").resolve(candidate).normalize();
        }
        return direct;
    }
}
