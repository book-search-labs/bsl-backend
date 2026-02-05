package com.bsl.search.service;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "search.rerank")
public class RerankPolicyProperties {
    private boolean enabled = true;
    private int maxTopK = 50;
    private int minCandidates = 5;
    private int minQueryLength = 2;
    private boolean skipIsbn = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getMaxTopK() {
        return maxTopK;
    }

    public void setMaxTopK(int maxTopK) {
        this.maxTopK = maxTopK;
    }

    public int getMinCandidates() {
        return minCandidates;
    }

    public void setMinCandidates(int minCandidates) {
        this.minCandidates = minCandidates;
    }

    public int getMinQueryLength() {
        return minQueryLength;
    }

    public void setMinQueryLength(int minQueryLength) {
        this.minQueryLength = minQueryLength;
    }

    public boolean isSkipIsbn() {
        return skipIsbn;
    }

    public void setSkipIsbn(boolean skipIsbn) {
        this.skipIsbn = skipIsbn;
    }
}
