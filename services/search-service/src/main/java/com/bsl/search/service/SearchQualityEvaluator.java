package com.bsl.search.service;

import org.springframework.stereotype.Component;

@Component
public class SearchQualityEvaluator {
    private final SearchQualityProperties properties;

    public SearchQualityEvaluator(SearchQualityProperties properties) {
        this.properties = properties;
    }

    public QualityEvaluation evaluate(int hits, double topScore) {
        if (hits <= 0) {
            return new QualityEvaluation("ZERO_RESULTS", 0, 0.0d);
        }

        if (hits < Math.max(properties.getLowResultsHitsThreshold(), 1)
            && topScore < properties.getLowResultsTopScoreThreshold()) {
            return new QualityEvaluation("LOW_RESULTS", hits, topScore);
        }

        return QualityEvaluation.pass(hits, topScore);
    }

    public static class QualityEvaluation {
        private final String reason;
        private final int hits;
        private final double topScore;

        private QualityEvaluation(String reason, int hits, double topScore) {
            this.reason = reason;
            this.hits = hits;
            this.topScore = topScore;
        }

        public static QualityEvaluation pass(int hits, double topScore) {
            return new QualityEvaluation(null, hits, topScore);
        }

        public boolean shouldEnhance() {
            return reason != null;
        }

        public String getReason() {
            return reason;
        }

        public int getHits() {
            return hits;
        }

        public double getTopScore() {
            return topScore;
        }
    }
}
