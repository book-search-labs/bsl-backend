package com.bsl.outboxrelay.config;

import java.util.HashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "outbox.relay")
public class OutboxRelayProperties {
    private boolean enabled = true;
    private int batchSize = 200;
    private long pollIntervalMs = 1000;
    private int maxRetries = 3;
    private long backoffMs = 200;
    private boolean dlqEnabled = true;
    private String dlqSuffix = ".dlq";
    private String producerName = "outbox-relay";
    private Map<String, String> topicMapping = new HashMap<>();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public long getPollIntervalMs() {
        return pollIntervalMs;
    }

    public void setPollIntervalMs(long pollIntervalMs) {
        this.pollIntervalMs = pollIntervalMs;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public long getBackoffMs() {
        return backoffMs;
    }

    public void setBackoffMs(long backoffMs) {
        this.backoffMs = backoffMs;
    }

    public boolean isDlqEnabled() {
        return dlqEnabled;
    }

    public void setDlqEnabled(boolean dlqEnabled) {
        this.dlqEnabled = dlqEnabled;
    }

    public String getDlqSuffix() {
        return dlqSuffix;
    }

    public void setDlqSuffix(String dlqSuffix) {
        this.dlqSuffix = dlqSuffix;
    }

    public String getProducerName() {
        return producerName;
    }

    public void setProducerName(String producerName) {
        this.producerName = producerName;
    }

    public Map<String, String> getTopicMapping() {
        return topicMapping;
    }

    public void setTopicMapping(Map<String, String> topicMapping) {
        this.topicMapping = topicMapping;
    }
}
