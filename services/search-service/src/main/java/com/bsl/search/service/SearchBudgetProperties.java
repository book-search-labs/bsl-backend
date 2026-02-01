package com.bsl.search.service;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "search.budget")
public class SearchBudgetProperties {
    private boolean enabled = true;
    private double lexicalShare = 0.5;
    private double vectorShare = 0.3;
    private double rerankShare = 0.2;
    private int minStageMs = 20;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public double getLexicalShare() {
        return lexicalShare;
    }

    public void setLexicalShare(double lexicalShare) {
        this.lexicalShare = lexicalShare;
    }

    public double getVectorShare() {
        return vectorShare;
    }

    public void setVectorShare(double vectorShare) {
        this.vectorShare = vectorShare;
    }

    public double getRerankShare() {
        return rerankShare;
    }

    public void setRerankShare(double rerankShare) {
        this.rerankShare = rerankShare;
    }

    public int getMinStageMs() {
        return minStageMs;
    }

    public void setMinStageMs(int minStageMs) {
        this.minStageMs = minStageMs;
    }
}
