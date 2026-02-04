package com.bsl.search.merge;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class RrfFusion {
    private RrfFusion() {
    }

    public static List<Candidate> fuse(Map<String, Integer> lexRanks, Map<String, Integer> vecRanks, int k) {
        return fuse(lexRanks, vecRanks, k, Map.of(), Map.of());
    }

    public static List<Candidate> fuse(
        Map<String, Integer> lexRanks,
        Map<String, Integer> vecRanks,
        int k,
        Map<String, Double> lexScores,
        Map<String, Double> vecScores
    ) {
        Map<String, MutableCandidate> candidates = new HashMap<>();

        for (Map.Entry<String, Integer> entry : lexRanks.entrySet()) {
            MutableCandidate candidate = candidates.computeIfAbsent(entry.getKey(), MutableCandidate::new);
            int rank = entry.getValue();
            candidate.lexRank = rank;
            candidate.score += 1.0 / (k + rank);
            candidate.bm25Score = lexScores == null ? null : lexScores.get(entry.getKey());
        }

        for (Map.Entry<String, Integer> entry : vecRanks.entrySet()) {
            MutableCandidate candidate = candidates.computeIfAbsent(entry.getKey(), MutableCandidate::new);
            int rank = entry.getValue();
            candidate.vecRank = rank;
            candidate.score += 1.0 / (k + rank);
            candidate.vecScore = vecScores == null ? null : vecScores.get(entry.getKey());
        }

        List<MutableCandidate> mutable = new ArrayList<>(candidates.values());
        mutable.sort(
            Comparator.comparingDouble(MutableCandidate::getScore).reversed()
                .thenComparing(MutableCandidate::getDocId)
        );

        List<Candidate> fused = new ArrayList<>(mutable.size());
        for (int i = 0; i < mutable.size(); i++) {
            MutableCandidate candidate = mutable.get(i);
            fused.add(
                new Candidate(
                    candidate.docId,
                    candidate.score,
                    candidate.lexRank,
                    candidate.vecRank,
                    i + 1,
                    candidate.bm25Score,
                    candidate.vecScore
                )
            );
        }
        return fused;
    }

    public static final class Candidate {
        private final String docId;
        private final double score;
        private final Integer lexRank;
        private final Integer vecRank;
        private final Integer fusedRank;
        private final Double bm25Score;
        private final Double vecScore;

        public Candidate(
            String docId,
            double score,
            Integer lexRank,
            Integer vecRank,
            Integer fusedRank,
            Double bm25Score,
            Double vecScore
        ) {
            this.docId = docId;
            this.score = score;
            this.lexRank = lexRank;
            this.vecRank = vecRank;
            this.fusedRank = fusedRank;
            this.bm25Score = bm25Score;
            this.vecScore = vecScore;
        }

        public String getDocId() {
            return docId;
        }

        public double getScore() {
            return score;
        }

        public Integer getLexRank() {
            return lexRank;
        }

        public Integer getVecRank() {
            return vecRank;
        }

        public Integer getFusedRank() {
            return fusedRank;
        }

        public Double getBm25Score() {
            return bm25Score;
        }

        public Double getVecScore() {
            return vecScore;
        }
    }

    private static final class MutableCandidate {
        private final String docId;
        private double score;
        private Integer lexRank;
        private Integer vecRank;
        private Double bm25Score;
        private Double vecScore;

        private MutableCandidate(String docId) {
            this.docId = docId;
        }

        private String getDocId() {
            return docId;
        }

        private double getScore() {
            return score;
        }
    }
}
