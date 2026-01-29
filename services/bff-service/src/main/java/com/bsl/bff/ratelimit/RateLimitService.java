package com.bsl.bff.ratelimit;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class RateLimitService {
    private final RateLimiter rateLimiter;
    private final RateLimitProperties properties;

    public RateLimitService(ObjectProvider<org.springframework.data.redis.core.StringRedisTemplate> redisTemplate,
                            RateLimitProperties properties) {
        this.properties = properties;
        if ("redis".equalsIgnoreCase(properties.getBackend())) {
            org.springframework.data.redis.core.StringRedisTemplate template = redisTemplate.getIfAvailable();
            if (template != null) {
                this.rateLimiter = new RedisRateLimiter(template);
            } else {
                this.rateLimiter = new InMemoryRateLimiter();
            }
        } else {
            this.rateLimiter = new InMemoryRateLimiter();
        }
    }

    public boolean allow(String key, int limit) {
        return rateLimiter.tryAcquire(key, limit, properties.getWindowSeconds());
    }

    public RateLimitProperties getProperties() {
        return properties;
    }
}
