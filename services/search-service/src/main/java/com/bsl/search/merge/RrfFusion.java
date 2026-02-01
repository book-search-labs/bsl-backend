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
        Map<String, MutableCandidate> candidates = new HashMap<>();

        for (Map.Entry<String, Integer> entry : lexRanks.entrySet()) {
            MutableCandidate candidate = candidates.computeIfAbsent(entry.getKey(), MutableCandidate::new);
            int rank = entry.getValue();
            candidate.lexRank = rank;
            candidate.score += 1.0 / (k + rank);
        }

        for (Map.Entry<String, Integer> entry : vecRanks.entrySet()) {
            MutableCandidate candidate = candidates.computeIfAbsent(entry.getKey(), MutableCandidate::new);
            int rank = entry.getValue();
            candidate.vecRank = rank;
            candidate.score += 1.0 / (k + rank);
        }

        List<MutableCandidate> mutable = new ArrayList<>(candidates.values());
        mutable.sort(
            Comparator.comparingDouble(MutableCandidate::getScore).reversed()
                .thenComparing(MutableCandidate::getDocId)
        );

        List<Candidate> fused = new ArrayList<>(mutable.size());
        for (MutableCandidate candidate : mutable) {
            fused.add(new Candidate(candidate.docId, candidate.score, candidate.lexRank, candidate.vecRank));
        }
        return fused;
    }

    public static final class Candidate {
        private final String docId;
        private final double score;
        private final Integer lexRank;
        private final Integer vecRank;

        Candidate(String docId, double score, Integer lexRank, Integer vecRank) {
            this.docId = docId;
            this.score = score;
            this.lexRank = lexRank;
            this.vecRank = vecRank;
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
    }

    private static final class MutableCandidate {
        private final String docId;
        private double score;
        private Integer lexRank;
        private Integer vecRank;

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
