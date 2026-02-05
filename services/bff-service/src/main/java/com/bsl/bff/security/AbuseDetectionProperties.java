package com.bsl.bff.security;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "security.abuse")
public class AbuseDetectionProperties {
    private boolean enabled = false;
    private int windowSeconds = 60;
    private int errorThreshold = 20;
    private int blockSeconds = 600;
    private List<Integer> errorStatuses = new ArrayList<>(List.of(400, 401, 403, 404, 429));

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getWindowSeconds() {
        return windowSeconds;
    }

    public void setWindowSeconds(int windowSeconds) {
        this.windowSeconds = windowSeconds;
    }

    public int getErrorThreshold() {
        return errorThreshold;
    }

    public void setErrorThreshold(int errorThreshold) {
        this.errorThreshold = errorThreshold;
    }

    public int getBlockSeconds() {
        return blockSeconds;
    }

    public void setBlockSeconds(int blockSeconds) {
        this.blockSeconds = blockSeconds;
    }

    public List<Integer> getErrorStatuses() {
        return errorStatuses;
    }

    public void setErrorStatuses(List<Integer> errorStatuses) {
        this.errorStatuses = errorStatuses;
    }
}
