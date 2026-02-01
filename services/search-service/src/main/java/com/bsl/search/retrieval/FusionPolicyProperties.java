package com.bsl.search.retrieval;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "search.fusion")
public class FusionPolicyProperties {
    private String defaultMethod = "rrf";
    private boolean experimentEnabled = false;
    private double weightedRate = 0.2;
    private double lexWeight = 1.0;
    private double vecWeight = 1.0;

    public String getDefaultMethod() {
        return defaultMethod;
    }

    public void setDefaultMethod(String defaultMethod) {
        this.defaultMethod = defaultMethod;
    }

    public boolean isExperimentEnabled() {
        return experimentEnabled;
    }

    public void setExperimentEnabled(boolean experimentEnabled) {
        this.experimentEnabled = experimentEnabled;
    }

    public double getWeightedRate() {
        return weightedRate;
    }

    public void setWeightedRate(double weightedRate) {
        this.weightedRate = weightedRate;
    }

    public double getLexWeight() {
        return lexWeight;
    }

    public void setLexWeight(double lexWeight) {
        this.lexWeight = lexWeight;
    }

    public double getVecWeight() {
        return vecWeight;
    }

    public void setVecWeight(double vecWeight) {
        this.vecWeight = vecWeight;
    }
}
