package com.bsl.ranking.service;

import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.api.dto.RerankResponse;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ToyRerankService {
    private static final int DEFAULT_SIZE = 10;
    private static final double RANK_BASE = 60.0;

    public RerankResponse rerank(RerankRequest request, String traceId, String requestId) {
        long started = System.nanoTime();

        int size = DEFAULT_SIZE;
        if (request.getOptions() != null && request.getOptions().getSize() != null) {
            size = Math.max(request.getOptions().getSize(), 0);
        }

        List<ScoreEntry> scored = new ArrayList<>();
        for (RerankRequest.Candidate candidate : request.getCandidates()) {
            if (candidate == null || candidate.getDocId() == null || candidate.getDocId().isEmpty()) {
                continue;
            }
            ScoreEntry entry = score(candidate);
            scored.add(entry);
        }

        scored.sort(
            Comparator.comparingDouble(ScoreEntry::getScore).reversed()
                .thenComparing(entry -> nullSafeRank(entry.getLexRank()))
                .thenComparing(entry -> nullSafeRank(entry.getVecRank()))
                .thenComparing(ScoreEntry::getDocId)
        );

        int limit = Math.min(size, scored.size());
        List<RerankResponse.Hit> hits = new ArrayList<>(limit);
        for (int i = 0; i < limit; i++) {
            ScoreEntry entry = scored.get(i);
            RerankResponse.Hit hit = new RerankResponse.Hit();
            hit.setDocId(entry.getDocId());
            hit.setScore(entry.getScore());
            hit.setRank(i + 1);

            RerankResponse.Debug debug = new RerankResponse.Debug();
            debug.setLexRank(entry.getLexRank());
            debug.setVecRank(entry.getVecRank());
            debug.setBase(entry.getBase());
            debug.setLexBonus(entry.getLexBonus());
            debug.setVecBonus(entry.getVecBonus());
            debug.setFreshnessBonus(entry.getFreshnessBonus());
            debug.setSlotBonus(entry.getSlotBonus());
            hit.setDebug(debug);

            hits.add(hit);
        }

        long tookMs = (System.nanoTime() - started) / 1_000_000L;
        RerankResponse response = new RerankResponse();
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs(tookMs);
        response.setModel("toy_rerank_v1");
        response.setHits(hits);
        return response;
    }

    private ScoreEntry score(RerankRequest.Candidate candidate) {
        RerankRequest.Features features = candidate.getFeatures();
        Integer lexRank = features == null ? null : features.getLexRank();
        Integer vecRank = features == null ? null : features.getVecRank();
        Double baseScore = features == null ? null : features.getRrfScore();
        Integer issuedYear = features == null ? null : features.getIssuedYear();
        Integer volume = features == null ? null : features.getVolume();
        List<String> editionLabels = features == null ? null : features.getEditionLabels();

        double base = baseScore == null ? 0.0 : baseScore;
        double lexBonus = lexRank == null ? 0.0 : 1.0 / (RANK_BASE + lexRank);
        double vecBonus = vecRank == null ? 0.0 : 1.0 / (RANK_BASE + vecRank);
        double freshnessBonus = computeFreshnessBonus(issuedYear);
        double slotBonus = computeSlotBonus(volume, editionLabels);

        double score = base + (2.0 * lexBonus) + vecBonus + (0.2 * freshnessBonus) + slotBonus;

        ScoreEntry entry = new ScoreEntry(candidate.getDocId(), score);
        entry.setLexRank(lexRank);
        entry.setVecRank(vecRank);
        entry.setBase(base);
        entry.setLexBonus(lexBonus);
        entry.setVecBonus(vecBonus);
        entry.setFreshnessBonus(freshnessBonus);
        entry.setSlotBonus(slotBonus);
        return entry;
    }

    private double computeFreshnessBonus(Integer issuedYear) {
        if (issuedYear == null) {
            return 0.0;
        }
        double raw = (issuedYear - 1980) / 100.0;
        if (raw < 0.0) {
            return 0.0;
        }
        if (raw > 0.5) {
            return 0.5;
        }
        return raw;
    }

    private double computeSlotBonus(Integer volume, List<String> editionLabels) {
        double bonus = 0.0;
        if (volume != null && volume > 0) {
            bonus += 0.10;
        }
        if (editionLabels != null) {
            for (String label : editionLabels) {
                if (label != null && label.equalsIgnoreCase("recover")) {
                    bonus += 0.05;
                    break;
                }
            }
        }
        return bonus;
    }

    private int nullSafeRank(Integer rank) {
        return rank == null ? Integer.MAX_VALUE : rank;
    }

    private static class ScoreEntry {
        private final String docId;
        private final double score;
        private Integer lexRank;
        private Integer vecRank;
        private double base;
        private double lexBonus;
        private double vecBonus;
        private double freshnessBonus;
        private double slotBonus;

        private ScoreEntry(String docId, double score) {
            this.docId = docId;
            this.score = score;
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

        public void setLexRank(Integer lexRank) {
            this.lexRank = lexRank;
        }

        public Integer getVecRank() {
            return vecRank;
        }

        public void setVecRank(Integer vecRank) {
            this.vecRank = vecRank;
        }

        public double getBase() {
            return base;
        }

        public void setBase(double base) {
            this.base = base;
        }

        public double getLexBonus() {
            return lexBonus;
        }

        public void setLexBonus(double lexBonus) {
            this.lexBonus = lexBonus;
        }

        public double getVecBonus() {
            return vecBonus;
        }

        public void setVecBonus(double vecBonus) {
            this.vecBonus = vecBonus;
        }

        public double getFreshnessBonus() {
            return freshnessBonus;
        }

        public void setFreshnessBonus(double freshnessBonus) {
            this.freshnessBonus = freshnessBonus;
        }

        public double getSlotBonus() {
            return slotBonus;
        }

        public void setSlotBonus(double slotBonus) {
            this.slotBonus = slotBonus;
        }
    }
}
