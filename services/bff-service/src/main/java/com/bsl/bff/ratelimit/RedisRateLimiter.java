package com.bsl.bff.ratelimit;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisRateLimiter implements RateLimiter {
    private final StringRedisTemplate redisTemplate;

    public RedisRateLimiter(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    @Override
    public boolean tryAcquire(String key, int limit, int windowSeconds) {
        long windowId = System.currentTimeMillis() / 1000L / Math.max(windowSeconds, 1);
        String redisKey = "rl:" + key + ":" + windowId;
        Long count = redisTemplate.opsForValue().increment(redisKey);
        if (count != null && count == 1L) {
            redisTemplate.expire(redisKey, Duration.ofSeconds(windowSeconds));
        }
        return count != null && count <= limit;
    }
}
