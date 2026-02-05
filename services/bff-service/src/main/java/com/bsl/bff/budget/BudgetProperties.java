package com.bsl.bff.budget;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.budget")
public class BudgetProperties {
    private boolean enabled = true;
    private int searchMs = 800;
    private int chatMs = 1200;
    private int defaultMs = 600;
    private int downstreamReserveMs = 50;
    private int minDownstreamTimeoutMs = 50;
    private int maxDownstreamTimeoutMs = 1500;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getSearchMs() {
        return searchMs;
    }

    public void setSearchMs(int searchMs) {
        this.searchMs = searchMs;
    }

    public int getChatMs() {
        return chatMs;
    }

    public void setChatMs(int chatMs) {
        this.chatMs = chatMs;
    }

    public int getDefaultMs() {
        return defaultMs;
    }

    public void setDefaultMs(int defaultMs) {
        this.defaultMs = defaultMs;
    }

    public int getDownstreamReserveMs() {
        return downstreamReserveMs;
    }

    public void setDownstreamReserveMs(int downstreamReserveMs) {
        this.downstreamReserveMs = downstreamReserveMs;
    }

    public int getMinDownstreamTimeoutMs() {
        return minDownstreamTimeoutMs;
    }

    public void setMinDownstreamTimeoutMs(int minDownstreamTimeoutMs) {
        this.minDownstreamTimeoutMs = minDownstreamTimeoutMs;
    }

    public int getMaxDownstreamTimeoutMs() {
        return maxDownstreamTimeoutMs;
    }

    public void setMaxDownstreamTimeoutMs(int maxDownstreamTimeoutMs) {
        this.maxDownstreamTimeoutMs = maxDownstreamTimeoutMs;
    }
}
