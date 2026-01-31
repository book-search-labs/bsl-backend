package com.bsl.search.resilience;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "search.resilience")
public class SearchResilienceProperties {
    private int vectorFailureThreshold = 3;
    private long vectorOpenMs = 30000;
    private int rerankFailureThreshold = 3;
    private long rerankOpenMs = 30000;
    private int rerankHedgeDelayMs = 60;

    public int getVectorFailureThreshold() {
        return vectorFailureThreshold;
    }

    public void setVectorFailureThreshold(int vectorFailureThreshold) {
        this.vectorFailureThreshold = vectorFailureThreshold;
    }

    public long getVectorOpenMs() {
        return vectorOpenMs;
    }

    public void setVectorOpenMs(long vectorOpenMs) {
        this.vectorOpenMs = vectorOpenMs;
    }

    public int getRerankFailureThreshold() {
        return rerankFailureThreshold;
    }

    public void setRerankFailureThreshold(int rerankFailureThreshold) {
        this.rerankFailureThreshold = rerankFailureThreshold;
    }

    public long getRerankOpenMs() {
        return rerankOpenMs;
    }

    public void setRerankOpenMs(long rerankOpenMs) {
        this.rerankOpenMs = rerankOpenMs;
    }

    public int getRerankHedgeDelayMs() {
        return rerankHedgeDelayMs;
    }

    public void setRerankHedgeDelayMs(int rerankHedgeDelayMs) {
        this.rerankHedgeDelayMs = rerankHedgeDelayMs;
    }
}
