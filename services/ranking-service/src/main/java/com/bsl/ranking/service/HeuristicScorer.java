package com.bsl.ranking.service;

import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.api.dto.RerankResponse;
import java.util.List;
import java.util.Map;

public final class HeuristicScorer {
    private static final double RANK_BASE = 60.0;

    private HeuristicScorer() {
    }

    public static ScoreResult score(RerankRequest.Candidate candidate) {
        RerankRequest.Features features = candidate.getFeatures();
        Map<String, Double> featureMap = Map.of(
            "rrf_score", features == null || features.getRrfScore() == null ? 0.0 : features.getRrfScore(),
            "lex_rank", features == null || features.getLexRank() == null ? 0.0 : features.getLexRank().doubleValue(),
            "vec_rank", features == null || features.getVecRank() == null ? 0.0 : features.getVecRank().doubleValue(),
            "issued_year", features == null || features.getIssuedYear() == null ? 0.0 : features.getIssuedYear().doubleValue(),
            "volume", features == null || features.getVolume() == null ? 0.0 : features.getVolume().doubleValue()
        );
        return score(candidate.getDocId(), featureMap, features == null ? null : features.getEditionLabels());
    }

    public static ScoreResult score(String docId, Map<String, Double> features, List<String> editionLabels) {
        Double lexRankRaw = features.get("lex_rank");
        Double vecRankRaw = features.get("vec_rank");
        Double baseScore = features.get("rrf_score");
        Double issuedYearRaw = features.get("issued_year");
        Double volumeRaw = features.get("volume");
        Double ctr = features.get("ctr_7d");
        Double popularity = features.get("popularity_30d");

        Integer lexRank = lexRankRaw == null ? null : lexRankRaw.intValue();
        Integer vecRank = vecRankRaw == null ? null : vecRankRaw.intValue();
        Integer issuedYear = issuedYearRaw == null ? null : issuedYearRaw.intValue();
        Integer volume = volumeRaw == null ? null : volumeRaw.intValue();

        double base = baseScore == null ? 0.0 : baseScore;
        double lexBonus = lexRank == null ? 0.0 : 1.0 / (RANK_BASE + lexRank);
        double vecBonus = vecRank == null ? 0.0 : 1.0 / (RANK_BASE + vecRank);
        double freshnessBonus = computeFreshnessBonus(issuedYear);
        double slotBonus = computeSlotBonus(volume, editionLabels);
        double ctrBonus = ctr == null ? 0.0 : 0.05 * ctr;
        double popularityBonus = popularity == null ? 0.0 : 0.02 * popularity;

        double score = base + (2.0 * lexBonus) + vecBonus + (0.2 * freshnessBonus) + slotBonus + ctrBonus + popularityBonus;

        return new ScoreResult(
            docId,
            score,
            lexRank,
            vecRank,
            base,
            lexBonus,
            vecBonus,
            freshnessBonus,
            slotBonus,
            ctrBonus,
            popularityBonus
        );
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
        debug.setCtrBonus(result.ctrBonus());
        debug.setPopularityBonus(result.popularityBonus());
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
        double slotBonus,
        double ctrBonus,
        double popularityBonus
    ) {}
}
