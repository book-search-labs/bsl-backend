package com.bsl.search.experiment;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "search.experiments")
public class SearchExperimentProperties {
    private boolean enabled = false;
    private double exploreRate = 0.01;
    private int shuffleStart = 5;
    private int shuffleEnd = 20;
    private int minResults = 20;
    private int minQueryLength = 2;
    private boolean excludeIsbn = true;
    private boolean excludeQuoted = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public double getExploreRate() {
        return exploreRate;
    }

    public void setExploreRate(double exploreRate) {
        this.exploreRate = exploreRate;
    }

    public int getShuffleStart() {
        return shuffleStart;
    }

    public void setShuffleStart(int shuffleStart) {
        this.shuffleStart = shuffleStart;
    }

    public int getShuffleEnd() {
        return shuffleEnd;
    }

    public void setShuffleEnd(int shuffleEnd) {
        this.shuffleEnd = shuffleEnd;
    }

    public int getMinResults() {
        return minResults;
    }

    public void setMinResults(int minResults) {
        this.minResults = minResults;
    }

    public int getMinQueryLength() {
        return minQueryLength;
    }

    public void setMinQueryLength(int minQueryLength) {
        this.minQueryLength = minQueryLength;
    }

    public boolean isExcludeIsbn() {
        return excludeIsbn;
    }

    public void setExcludeIsbn(boolean excludeIsbn) {
        this.excludeIsbn = excludeIsbn;
    }

    public boolean isExcludeQuoted() {
        return excludeQuoted;
    }

    public void setExcludeQuoted(boolean excludeQuoted) {
        this.excludeQuoted = excludeQuoted;
    }
}
