package com.bsl.autocomplete.cache;

import com.bsl.autocomplete.api.dto.AutocompleteResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class AutocompleteCacheService {
    private static final Logger logger = LoggerFactory.getLogger(AutocompleteCacheService.class);
    private static final TypeReference<List<CacheSuggestion>> LIST_TYPE = new TypeReference<>() {};

    private final ObjectMapper objectMapper;
    private final ObjectProvider<StringRedisTemplate> redisProvider;
    private final AutocompleteCacheProperties properties;

    public AutocompleteCacheService(
        ObjectMapper objectMapper,
        ObjectProvider<StringRedisTemplate> redisProvider,
        AutocompleteCacheProperties properties
    ) {
        this.objectMapper = objectMapper;
        this.redisProvider = redisProvider;
        this.properties = properties;
    }

    public Optional<List<AutocompleteResponse.Suggestion>> get(String query, int size) {
        if (!properties.isEnabled()) {
            return Optional.empty();
        }
        StringRedisTemplate redis = redisProvider.getIfAvailable();
        if (redis == null) {
            return Optional.empty();
        }
        String key = keyFor(query);
        if (key == null) {
            return Optional.empty();
        }
        try {
            String payload = redis.opsForValue().get(key);
            if (payload == null || payload.isBlank()) {
                return Optional.empty();
            }
            List<CacheSuggestion> cached = objectMapper.readValue(payload, LIST_TYPE);
            if (cached.size() < size) {
                return Optional.empty();
            }
            List<AutocompleteResponse.Suggestion> mapped = new ArrayList<>();
            int limit = Math.min(size, cached.size());
            for (int i = 0; i < limit; i++) {
                CacheSuggestion item = cached.get(i);
                AutocompleteResponse.Suggestion suggestion = new AutocompleteResponse.Suggestion();
                suggestion.setText(item.text);
                suggestion.setScore(item.score);
                suggestion.setSuggestId(item.suggestId);
                suggestion.setType(item.type);
                suggestion.setTargetDocId(item.targetDocId);
                suggestion.setTargetId(item.targetId);
                suggestion.setSource("redis");
                mapped.add(suggestion);
            }
            return Optional.of(mapped);
        } catch (Exception ex) {
            logger.debug("Autocomplete cache read failed: {}", ex.getMessage());
            return Optional.empty();
        }
    }

    public void put(String query, List<AutocompleteResponse.Suggestion> suggestions) {
        if (!properties.isEnabled()) {
            return;
        }
        StringRedisTemplate redis = redisProvider.getIfAvailable();
        if (redis == null) {
            return;
        }
        String key = keyFor(query);
        if (key == null || suggestions == null || suggestions.isEmpty()) {
            return;
        }
        int maxItems = properties.getMaxItems();
        List<CacheSuggestion> items = new ArrayList<>();
        for (AutocompleteResponse.Suggestion suggestion : suggestions) {
            if (suggestion == null || suggestion.getText() == null || suggestion.getText().isBlank()) {
                continue;
            }
            CacheSuggestion cached = new CacheSuggestion();
            cached.text = suggestion.getText();
            cached.score = suggestion.getScore();
            cached.suggestId = suggestion.getSuggestId();
            cached.type = suggestion.getType();
            cached.targetDocId = suggestion.getTargetDocId();
            cached.targetId = suggestion.getTargetId();
            items.add(cached);
            if (items.size() >= maxItems) {
                break;
            }
        }
        if (items.isEmpty()) {
            return;
        }
        try {
            String payload = objectMapper.writeValueAsString(items);
            redis.opsForValue().set(key, payload, Duration.ofSeconds(properties.getTtlSeconds()));
        } catch (JsonProcessingException ex) {
            logger.debug("Failed to serialize autocomplete cache payload: {}", ex.getMessage());
        } catch (Exception ex) {
            logger.debug("Autocomplete cache write failed: {}", ex.getMessage());
        }
    }

    public String keyFor(String query) {
        if (query == null) {
            return null;
        }
        String normalized = query.trim().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty() || normalized.length() > properties.getMaxPrefixLength()) {
            return null;
        }
        String prefix = properties.getKeyPrefix();
        if (prefix == null) {
            prefix = "";
        }
        return prefix + normalized;
    }

    private static class CacheSuggestion {
        public String text;
        public double score;
        public String suggestId;
        public String type;
        public String targetId;
        public String targetDocId;
    }
}
