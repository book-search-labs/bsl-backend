package com.bsl.ranking.service;

import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.api.dto.RerankResponse;
import java.util.List;

public final class HeuristicScorer {
    private static final double RANK_BASE = 60.0;

    private HeuristicScorer() {
    }

    public static ScoreResult score(RerankRequest.Candidate candidate) {
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

        return new ScoreResult(candidate.getDocId(), score, lexRank, vecRank, base, lexBonus, vecBonus, freshnessBonus, slotBonus);
    }

    public static RerankResponse.Debug toDebug(ScoreResult result) {
        RerankResponse.Debug debug = new RerankResponse.Debug();
        debug.setLexRank(result.lexRank());
        debug.setVecRank(result.vecRank());
        debug.setBase(result.base());
        debug.setLexBonus(result.lexBonus());
        debug.setVecBonus(result.vecBonus());
        debug.setFreshnessBonus(result.freshnessBonus());
        debug.setSlotBonus(result.slotBonus());
        return debug;
    }

    private static double computeFreshnessBonus(Integer issuedYear) {
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

    private static double computeSlotBonus(Integer volume, List<String> editionLabels) {
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

    public record ScoreResult(
        String docId,
        double score,
        Integer lexRank,
        Integer vecRank,
        double base,
        double lexBonus,
        double vecBonus,
        double freshnessBonus,
        double slotBonus
    ) {}
}
