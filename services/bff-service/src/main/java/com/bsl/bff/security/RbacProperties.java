package com.bsl.bff.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.rbac")
public class RbacProperties {
    private boolean enabled = true;
    private long cacheTtlMs = 30000;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public long getCacheTtlMs() {
        return cacheTtlMs;
    }

    public void setCacheTtlMs(long cacheTtlMs) {
        this.cacheTtlMs = cacheTtlMs;
    }
}
