package com.bsl.ranking.service;

import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.api.dto.RerankResponse;
import com.bsl.ranking.features.EnrichedCandidate;
import com.bsl.ranking.features.FeatureFetcher;
import com.bsl.ranking.features.FeatureSpec;
import com.bsl.ranking.features.FeatureSpecService;
import com.bsl.ranking.mis.MisClient;
import com.bsl.ranking.mis.MisUnavailableException;
import com.bsl.ranking.mis.dto.MisScoreResponse;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class RerankService {
    private static final Logger log = LoggerFactory.getLogger(RerankService.class);
    private static final int DEFAULT_SIZE = 10;

    private final MisClient misClient;
    private final FeatureFetcher featureFetcher;
    private final FeatureSpecService featureSpecService;
    private final RerankGuardrailsProperties guardrails;

    public RerankService(
        MisClient misClient,
        FeatureFetcher featureFetcher,
        FeatureSpecService featureSpecService,
        RerankGuardrailsProperties guardrails
    ) {
        this.misClient = misClient;
        this.featureFetcher = featureFetcher;
        this.featureSpecService = featureSpecService;
        this.guardrails = guardrails;
    }

    public RerankResponse rerank(RerankRequest request, String traceId, String requestId) {
        long started = System.nanoTime();
        List<String> reasonCodes = new ArrayList<>();
        boolean debugEnabled = request.getOptions() != null && Boolean.TRUE.equals(request.getOptions().getDebug());
        boolean rerankRequested = request.getOptions() == null || request.getOptions().getRerank() == null
            || Boolean.TRUE.equals(request.getOptions().getRerank());

        String queryText = request.getQuery() == null ? null : request.getQuery().getText();
        List<RerankRequest.Candidate> candidates = collectCandidates(request);
        int candidatesIn = candidates.size();
        candidates = applyCandidateLimit(candidates, reasonCodes);
        int candidatesUsed = candidates.size();

        int size = resolveSize(request, reasonCodes);
        int timeoutMs = resolveTimeoutMs(request, reasonCodes);

        List<EnrichedCandidate> enrichedCandidates = featureFetcher.enrich(candidates, queryText);

        boolean misEligible = misClient.isEnabled()
            && rerankRequested
            && candidatesUsed >= guardrails.getMinCandidatesForMis()
            && (queryText == null || queryText.trim().length() >= guardrails.getMinQueryLengthForMis())
            && timeoutMs > 0;

        List<ScoredCandidate> scored;
        String modelId;
        boolean rerankApplied = false;

        if (!rerankRequested) {
            reasonCodes.add("rerank_disabled");
        }
        if (!misClient.isEnabled()) {
            reasonCodes.add("mis_disabled");
        }
        if (candidatesUsed < guardrails.getMinCandidatesForMis()) {
            reasonCodes.add("mis_skipped_min_candidates");
        }
        if (queryText != null && queryText.trim().length() < guardrails.getMinQueryLengthForMis()) {
            reasonCodes.add("mis_skipped_short_query");
        }
        if (timeoutMs <= 0) {
            reasonCodes.add("timeout_budget_exhausted");
        }

        if (misEligible) {
            try {
                List<EnrichedCandidate> misCandidates = applyMisLimit(enrichedCandidates, reasonCodes);
                List<RerankRequest.Candidate> misRequestCandidates = buildMisCandidates(misCandidates);
                MisScoreResponse scoreResponse = misClient.score(
                    queryText,
                    misRequestCandidates,
                    timeoutMs,
                    debugEnabled,
                    traceId,
                    requestId
                );
                if (scoreResponse == null || scoreResponse.getScores() == null) {
                    throw new MisUnavailableException("mis returned empty scores");
                }
                List<Double> scores = scoreResponse.getScores();
                if (scores.size() != misCandidates.size()) {
                    throw new MisUnavailableException("mis score size mismatch");
                }
                scored = buildScoredFromMis(misCandidates, scores);
                modelId = scoreResponse.getModel() == null ? "mis" : scoreResponse.getModel();
                rerankApplied = true;
            } catch (MisUnavailableException ex) {
                log.debug("MIS unavailable, falling back to heuristic scorer", ex);
                reasonCodes.add("mis_error");
                scored = buildScoredHeuristic(enrichedCandidates);
                modelId = "toy_rerank_v1";
            }
        } else {
            scored = buildScoredHeuristic(enrichedCandidates);
            modelId = "toy_rerank_v1";
        }

        scored.sort(
            Comparator.comparingDouble(ScoredCandidate::score).reversed()
                .thenComparing(entry -> nullSafeRank(entry.lexRank()))
                .thenComparing(entry -> nullSafeRank(entry.vecRank()))
                .thenComparing(ScoredCandidate::docId)
        );

        int limit = Math.min(size, scored.size());
        List<RerankResponse.Hit> hits = new ArrayList<>(limit);
        for (int i = 0; i < limit; i++) {
            ScoredCandidate entry = scored.get(i);
            RerankResponse.Hit hit = new RerankResponse.Hit();
            hit.setDocId(entry.docId());
            hit.setScore(entry.score());
            hit.setRank(i + 1);
            if (debugEnabled) {
                hit.setDebug(buildHitDebug(entry, reasonCodes));
            }
            hits.add(hit);
        }

        long tookMs = (System.nanoTime() - started) / 1_000_000L;
        RerankResponse response = new RerankResponse();
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs(tookMs);
        response.setModel(modelId);
        response.setHits(hits);
        if (debugEnabled) {
            response.setDebug(buildResponseDebug(modelId, reasonCodes, candidatesIn, candidatesUsed, timeoutMs, rerankApplied));
        }
        return response;
    }

    private List<RerankRequest.Candidate> collectCandidates(RerankRequest request) {
        List<RerankRequest.Candidate> filtered = new ArrayList<>();
        if (request.getCandidates() == null) {
            return filtered;
        }
        for (RerankRequest.Candidate candidate : request.getCandidates()) {
            if (candidate == null || isBlank(candidate.getDocId())) {
                continue;
            }
            filtered.add(candidate);
        }
        return filtered;
    }

    private int resolveSize(RerankRequest request, List<String> reasonCodes) {
        int size = DEFAULT_SIZE;
        if (request.getOptions() != null && request.getOptions().getSize() != null) {
            size = Math.max(request.getOptions().getSize(), 0);
        }
        if (size > guardrails.getMaxTopN()) {
            size = guardrails.getMaxTopN();
            reasonCodes.add("size_capped");
        }
        return size;
    }

    private int resolveTimeoutMs(RerankRequest request, List<String> reasonCodes) {
        int timeoutMs = 0;
        if (request.getOptions() != null && request.getOptions().getTimeoutMs() != null) {
            timeoutMs = request.getOptions().getTimeoutMs();
        }
        if (timeoutMs <= 0) {
            timeoutMs = guardrails.getTimeoutMsMax();
        }
        if (timeoutMs > guardrails.getTimeoutMsMax()) {
            timeoutMs = guardrails.getTimeoutMsMax();
            reasonCodes.add("timeout_capped");
        }
        return timeoutMs;
    }

    private List<RerankRequest.Candidate> applyCandidateLimit(
        List<RerankRequest.Candidate> candidates,
        List<String> reasonCodes
    ) {
        if (candidates.size() > guardrails.getMaxCandidates()) {
            reasonCodes.add("candidates_capped");
            return new ArrayList<>(candidates.subList(0, guardrails.getMaxCandidates()));
        }
        return candidates;
    }

    private List<EnrichedCandidate> applyMisLimit(List<EnrichedCandidate> candidates, List<String> reasonCodes) {
        if (candidates.size() > guardrails.getMaxMisCandidates()) {
            reasonCodes.add("mis_candidates_capped");
            return new ArrayList<>(candidates.subList(0, guardrails.getMaxMisCandidates()));
        }
        return candidates;
    }

    private List<ScoredCandidate> buildScoredFromMis(List<EnrichedCandidate> candidates, List<Double> scores) {
        List<ScoredCandidate> scored = new ArrayList<>(candidates.size());
        for (int i = 0; i < candidates.size(); i++) {
            EnrichedCandidate candidate = candidates.get(i);
            double score = scores.get(i) == null ? 0.0 : scores.get(i);
            Integer lexRank = toInt(candidate.getRawFeatures().get("lex_rank"));
            Integer vecRank = toInt(candidate.getRawFeatures().get("vec_rank"));
            scored.add(new ScoredCandidate(candidate.getDocId(), score, lexRank, vecRank, candidate, null));
        }
        return scored;
    }

    private List<ScoredCandidate> buildScoredHeuristic(List<EnrichedCandidate> candidates) {
        List<ScoredCandidate> scored = new ArrayList<>(candidates.size());
        for (EnrichedCandidate candidate : candidates) {
            HeuristicScorer.ScoreResult result = HeuristicScorer.score(
                candidate.getDocId(),
                candidate.getFeatures(),
                candidate.getSource().getFeatures() == null ? null : candidate.getSource().getFeatures().getEditionLabels()
            );
            scored.add(new ScoredCandidate(candidate.getDocId(), result.score(), result.lexRank(), result.vecRank(), candidate, result));
        }
        return scored;
    }

    private List<RerankRequest.Candidate> buildMisCandidates(List<EnrichedCandidate> candidates) {
        List<RerankRequest.Candidate> output = new ArrayList<>(candidates.size());
        for (EnrichedCandidate candidate : candidates) {
            RerankRequest.Candidate rerankCandidate = new RerankRequest.Candidate();
            rerankCandidate.setDocId(candidate.getDocId());
            RerankRequest.Features features = new RerankRequest.Features();
            Map<String, Object> raw = candidate.getRawFeatures();
            features.setLexRank(toInt(raw.get("lex_rank")));
            features.setVecRank(toInt(raw.get("vec_rank")));
            features.setRrfScore(toDouble(raw.get("rrf_score")));
            features.setIssuedYear(toInt(raw.get("issued_year")));
            features.setVolume(toInt(raw.get("volume")));
            if (candidate.getSource().getFeatures() != null) {
                features.setEditionLabels(candidate.getSource().getFeatures().getEditionLabels());
            }
            rerankCandidate.setFeatures(features);
            output.add(rerankCandidate);
        }
        return output;
    }

    private RerankResponse.Debug buildHitDebug(ScoredCandidate scored, List<String> reasonCodes) {
        RerankResponse.Debug debug = new RerankResponse.Debug();
        EnrichedCandidate enriched = scored.enriched();
        if (scored.heuristicResult() != null) {
            debug = HeuristicScorer.toDebug(scored.heuristicResult());
        } else if (enriched != null) {
            debug.setLexRank(toInt(enriched.getRawFeatures().get("lex_rank")));
            debug.setVecRank(toInt(enriched.getRawFeatures().get("vec_rank")));
            debug.setBase(toDouble(enriched.getRawFeatures().get("rrf_score")));
        }
        if (enriched != null) {
            debug.setFeatures(enriched.getFeatures());
        }
        debug.setReasonCodes(reasonCodes);
        return debug;
    }

    private RerankResponse.DebugInfo buildResponseDebug(
        String modelId,
        List<String> reasonCodes,
        int candidatesIn,
        int candidatesUsed,
        int timeoutMs,
        boolean rerankApplied
    ) {
        FeatureSpec spec = featureSpecService.getSpec();
        RerankResponse.DebugInfo info = new RerankResponse.DebugInfo();
        info.setModelId(modelId);
        info.setFeatureSetVersion(spec == null ? null : spec.getFeatureSetVersion());
        info.setCandidatesIn(candidatesIn);
        info.setCandidatesUsed(candidatesUsed);
        info.setTimeoutMs(timeoutMs);
        info.setRerankApplied(rerankApplied);
        info.setReasonCodes(reasonCodes);
        return info;
    }

    private int nullSafeRank(Integer rank) {
        return rank == null ? Integer.MAX_VALUE : rank;
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private Integer toInt(Object raw) {
        if (raw instanceof Number number) {
            return number.intValue();
        }
        if (raw instanceof String text) {
            try {
                return Integer.parseInt(text.trim());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private Double toDouble(Object raw) {
        if (raw instanceof Number number) {
            return number.doubleValue();
        }
        if (raw instanceof String text) {
            try {
                return Double.parseDouble(text.trim());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private record ScoredCandidate(
        String docId,
        double score,
        Integer lexRank,
        Integer vecRank,
        EnrichedCandidate enriched,
        HeuristicScorer.ScoreResult heuristicResult
    ) {}
}
