package com.bsl.ranking.service;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "ranking.guardrails")
public class RerankGuardrailsProperties {
    private int maxCandidates = 200;
    private int maxTopN = 50;
    private int maxMisCandidates = 100;
    private int minCandidatesForMis = 5;
    private int minQueryLengthForMis = 2;
    private int timeoutMsMax = 500;

    public int getMaxCandidates() {
        return maxCandidates;
    }

    public void setMaxCandidates(int maxCandidates) {
        this.maxCandidates = maxCandidates;
    }

    public int getMaxTopN() {
        return maxTopN;
    }

    public void setMaxTopN(int maxTopN) {
        this.maxTopN = maxTopN;
    }

    public int getMaxMisCandidates() {
        return maxMisCandidates;
    }

    public void setMaxMisCandidates(int maxMisCandidates) {
        this.maxMisCandidates = maxMisCandidates;
    }

    public int getMinCandidatesForMis() {
        return minCandidatesForMis;
    }

    public void setMinCandidatesForMis(int minCandidatesForMis) {
        this.minCandidatesForMis = minCandidatesForMis;
    }

    public int getMinQueryLengthForMis() {
        return minQueryLengthForMis;
    }

    public void setMinQueryLengthForMis(int minQueryLengthForMis) {
        this.minQueryLengthForMis = minQueryLengthForMis;
    }

    public int getTimeoutMsMax() {
        return timeoutMsMax;
    }

    public void setTimeoutMsMax(int timeoutMsMax) {
        this.timeoutMsMax = timeoutMsMax;
    }
}
