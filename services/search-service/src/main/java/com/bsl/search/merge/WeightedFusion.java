package com.bsl.search.merge;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class WeightedFusion {
    private WeightedFusion() {
    }

    public static List<RrfFusion.Candidate> fuse(
        Map<String, Integer> lexRanks,
        Map<String, Integer> vecRanks,
        int k,
        double lexWeight,
        double vecWeight
    ) {
        Map<String, MutableCandidate> candidates = new HashMap<>();

        for (Map.Entry<String, Integer> entry : lexRanks.entrySet()) {
            MutableCandidate candidate = candidates.computeIfAbsent(entry.getKey(), MutableCandidate::new);
            int rank = entry.getValue();
            candidate.lexRank = rank;
            candidate.score += lexWeight * (1.0 / (k + rank));
        }

        for (Map.Entry<String, Integer> entry : vecRanks.entrySet()) {
            MutableCandidate candidate = candidates.computeIfAbsent(entry.getKey(), MutableCandidate::new);
            int rank = entry.getValue();
            candidate.vecRank = rank;
            candidate.score += vecWeight * (1.0 / (k + rank));
        }

        List<MutableCandidate> mutable = new ArrayList<>(candidates.values());
        mutable.sort(
            Comparator.comparingDouble(MutableCandidate::getScore).reversed()
                .thenComparing(MutableCandidate::getDocId)
        );

        List<RrfFusion.Candidate> fused = new ArrayList<>(mutable.size());
        for (MutableCandidate candidate : mutable) {
            fused.add(new RrfFusion.Candidate(candidate.docId, candidate.score, candidate.lexRank, candidate.vecRank));
        }
        return fused;
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
