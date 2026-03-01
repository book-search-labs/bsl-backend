package com.bsl.bff.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.ops-metrics")
public class OpsMetricsProperties {
    private boolean enabled = true;
    private String clickhouseUrl = "http://localhost:8123";
    private String clickhouseDatabase = "bsl_olap";
    private int timeoutMs = 1200;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getClickhouseUrl() {
        return clickhouseUrl;
    }

    public void setClickhouseUrl(String clickhouseUrl) {
        this.clickhouseUrl = clickhouseUrl;
    }

    public String getClickhouseDatabase() {
        return clickhouseDatabase;
    }

    public void setClickhouseDatabase(String clickhouseDatabase) {
        this.clickhouseDatabase = clickhouseDatabase;
    }

    public int getTimeoutMs() {
        return timeoutMs;
    }

    public void setTimeoutMs(int timeoutMs) {
        this.timeoutMs = timeoutMs;
    }
}
