package com.bsl.search.embed;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class EmbeddingCacheServiceTest {

    @Test
    void cacheHonorsNormalizeFlag() {
        EmbeddingProperties props = new EmbeddingProperties();
        EmbeddingProperties.Cache cache = new EmbeddingProperties.Cache();
        cache.setEnabled(true);
        cache.setNormalize(true);
        props.setCache(cache);

        EmbeddingCacheService service = new EmbeddingCacheService(props);
        service.put("Hello", List.of(0.1));
        assertTrue(service.get("hello").isPresent());

        EmbeddingProperties propsNoNorm = new EmbeddingProperties();
        EmbeddingProperties.Cache cacheNoNorm = new EmbeddingProperties.Cache();
        cacheNoNorm.setEnabled(true);
        cacheNoNorm.setNormalize(false);
        propsNoNorm.setCache(cacheNoNorm);

        EmbeddingCacheService noNormService = new EmbeddingCacheService(propsNoNorm);
        noNormService.put("Hello", List.of(0.2));
        assertFalse(noNormService.get("hello").isPresent());
    }
}
