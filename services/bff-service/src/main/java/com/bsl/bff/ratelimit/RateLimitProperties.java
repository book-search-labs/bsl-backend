package com.bsl.bff.ratelimit;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.rate-limit")
public class RateLimitProperties {
    private boolean enabled = true;
    private String backend = "memory";
    private int windowSeconds = 60;
    private int searchPerMinute = 60;
    private int autocompletePerMinute = 300;
    private int adminPerMinute = 30;
    private int defaultPerMinute = 60;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getBackend() {
        return backend;
    }

    public void setBackend(String backend) {
        this.backend = backend;
    }

    public int getWindowSeconds() {
        return windowSeconds;
    }

    public void setWindowSeconds(int windowSeconds) {
        this.windowSeconds = windowSeconds;
    }

    public int getSearchPerMinute() {
        return searchPerMinute;
    }

    public void setSearchPerMinute(int searchPerMinute) {
        this.searchPerMinute = searchPerMinute;
    }

    public int getAutocompletePerMinute() {
        return autocompletePerMinute;
    }

    public void setAutocompletePerMinute(int autocompletePerMinute) {
        this.autocompletePerMinute = autocompletePerMinute;
    }

    public int getAdminPerMinute() {
        return adminPerMinute;
    }

    public void setAdminPerMinute(int adminPerMinute) {
        this.adminPerMinute = adminPerMinute;
    }

    public int getDefaultPerMinute() {
        return defaultPerMinute;
    }

    public void setDefaultPerMinute(int defaultPerMinute) {
        this.defaultPerMinute = defaultPerMinute;
    }
}
