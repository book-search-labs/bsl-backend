package com.bsl.bff.ratelimit;

public interface RateLimiter {
    boolean tryAcquire(String key, int limit, int windowSeconds);
}
