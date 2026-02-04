package com.bsl.search.service;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "search.quality")
public class SearchQualityProperties {
    private int lowResultsHitsThreshold = 3;
    private double lowResultsTopScoreThreshold = 0.02;

    public int getLowResultsHitsThreshold() {
        return lowResultsHitsThreshold;
    }

    public void setLowResultsHitsThreshold(int lowResultsHitsThreshold) {
        this.lowResultsHitsThreshold = lowResultsHitsThreshold;
    }

    public double getLowResultsTopScoreThreshold() {
        return lowResultsTopScoreThreshold;
    }

    public void setLowResultsTopScoreThreshold(double lowResultsTopScoreThreshold) {
        this.lowResultsTopScoreThreshold = lowResultsTopScoreThreshold;
    }
}
