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
import io.micrometer.core.instrument.MeterRegistry;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class RerankService {
    private static final Logger log = LoggerFactory.getLogger(RerankService.class);
    private static final int DEFAULT_SIZE = 10;
    private static final int DEFAULT_STAGE1_TOP_K = 50;
    private static final double STAGE1_TIMEOUT_RATIO = 0.4;

    private final MisClient misClient;
    private final FeatureFetcher featureFetcher;
    private final FeatureSpecService featureSpecService;
    private final RerankGuardrailsProperties guardrails;
    private final RerankScoreCache rerankScoreCache;
    private final MeterRegistry meterRegistry;

    public RerankService(
        MisClient misClient,
        FeatureFetcher featureFetcher,
        FeatureSpecService featureSpecService,
        RerankGuardrailsProperties guardrails,
        RerankScoreCache rerankScoreCache,
        MeterRegistry meterRegistry
    ) {
        this.misClient = misClient;
        this.featureFetcher = featureFetcher;
        this.featureSpecService = featureSpecService;
        this.guardrails = guardrails;
        this.rerankScoreCache = rerankScoreCache;
        this.meterRegistry = meterRegistry;
    }

    public RerankResponse rerank(RerankRequest request, String traceId, String requestId, String traceparent) {
        long started = System.nanoTime();
        List<String> reasonCodes = new ArrayList<>();
        Map<String, Object> stageDetails = new LinkedHashMap<>();
        boolean debugEnabled = request.getOptions() != null && Boolean.TRUE.equals(request.getOptions().getDebug());
        boolean rerankRequested = request.getOptions() == null
            || request.getOptions().getRerank() == null
            || Boolean.TRUE.equals(request.getOptions().getRerank());

        String queryText = request.getQuery() == null ? null : request.getQuery().getText();
        List<RerankRequest.Candidate> candidates = collectCandidates(request);
        int candidatesIn = candidates.size();
        candidates = applyCandidateLimit(candidates, reasonCodes);
        int candidatesUsed = candidates.size();

        int size = resolveSize(request, reasonCodes);
        int timeoutMs = resolveTimeoutMs(request, reasonCodes);

        List<EnrichedCandidate> enrichedCandidates = featureFetcher.enrich(candidates, queryText);
        StagePlan stagePlan = resolveStagePlan(request, timeoutMs, candidatesUsed);

        List<ScoredCandidate> finalScored;
        String modelId;
        boolean rerankApplied;

        if (!rerankRequested) {
            reasonCodes.add("rerank_disabled");
            finalScored = buildScoredHeuristic(enrichedCandidates);
            modelId = "toy_rerank_v1";
            rerankApplied = false;
            stageDetails.put("stage1", stageDebugMap(StageResult.skipped(stagePlan.stage1, candidatesUsed, "skip_rerank_disabled")));
            stageDetails.put("stage2", stageDebugMap(StageResult.skipped(stagePlan.stage2, candidatesUsed, "skip_rerank_disabled")));
        } else {
            StageResult stage1Result = executeStage1(
                stagePlan.stage1,
                enrichedCandidates,
                queryText,
                debugEnabled,
                traceId,
                requestId,
                traceparent
            );
            if (stage1Result.reasonCode != null) {
                reasonCodes.add("stage1:" + stage1Result.reasonCode);
            }
            stageDetails.put("stage1", stageDebugMap(stage1Result));

            List<EnrichedCandidate> stage2Input = stage1Result.outputCandidates != null
                ? stage1Result.outputCandidates
                : enrichedCandidates;

            StageResult stage2Result = executeStage2(
                stagePlan.stage2,
                stage2Input,
                stage1Result,
                queryText,
                debugEnabled,
                traceId,
                requestId,
                traceparent
            );
            if (stage2Result.reasonCode != null) {
                reasonCodes.add("stage2:" + stage2Result.reasonCode);
            }
            stageDetails.put("stage2", stageDebugMap(stage2Result));

            finalScored = stage2Result.scored;
            if (finalScored == null || finalScored.isEmpty()) {
                if (stage1Result.scored != null && !stage1Result.scored.isEmpty()) {
                    finalScored = stage1Result.scored;
                } else {
                    finalScored = buildScoredHeuristic(enrichedCandidates);
                }
            }

            modelId = stage2Result.modelId;
            if (isBlank(modelId)) {
                modelId = stage1Result.modelId;
            }
            if (isBlank(modelId)) {
                modelId = "toy_rerank_v1";
            }
            rerankApplied = stage1Result.applied || stage2Result.applied;
        }

        sortScored(finalScored);

        int limit = Math.min(size, finalScored.size());
        List<RerankResponse.Hit> hits = new ArrayList<>(limit);
        for (int i = 0; i < limit; i++) {
            ScoredCandidate entry = finalScored.get(i);
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
            response.setDebug(
                buildResponseDebug(modelId, reasonCodes, candidatesIn, candidatesUsed, timeoutMs, rerankApplied, request, stageDetails)
            );
        }
        return response;
    }

    private StagePlan resolveStagePlan(RerankRequest request, int timeoutMs, int candidatesUsed) {
        RerankRequest.Options options = request.getOptions();
        RerankRequest.RerankConfig config = options == null ? null : options.getRerankConfig();

        boolean stage1Enabled = false;
        boolean stage2Enabled = true;
        Integer stage1TopK = null;
        Integer stage2TopK = null;
        String stage1Model = null;
        String stage2Model = options == null ? null : options.getModel();

        if (config != null) {
            if (config.getStage1() != null) {
                if (config.getStage1().getEnabled() != null) {
                    stage1Enabled = config.getStage1().getEnabled();
                }
                stage1TopK = config.getStage1().getTopK();
                stage1Model = trimToNull(config.getStage1().getModel());
            }
            if (config.getStage2() != null) {
                if (config.getStage2().getEnabled() != null) {
                    stage2Enabled = config.getStage2().getEnabled();
                }
                stage2TopK = config.getStage2().getTopK();
                if (config.getStage2().getModel() != null && !config.getStage2().getModel().isBlank()) {
                    stage2Model = config.getStage2().getModel();
                }
            }
            if (config.getModel() != null && !config.getModel().isBlank()) {
                stage2Model = config.getModel();
            }
        }

        int resolvedStage1TopK = resolveStageTopK(stage1TopK, Math.min(DEFAULT_STAGE1_TOP_K, candidatesUsed));
        int resolvedStage2TopK = resolveStageTopK(stage2TopK, candidatesUsed);
        int[] stageTimeouts = splitTimeout(timeoutMs, stage1Enabled, stage2Enabled);

        ResolvedStage stage1 = new ResolvedStage(stage1Enabled, resolvedStage1TopK, stageTimeouts[0], stage1Model);
        ResolvedStage stage2 = new ResolvedStage(stage2Enabled, resolvedStage2TopK, stageTimeouts[1], trimToNull(stage2Model));
        return new StagePlan(stage1, stage2);
    }

    private int resolveStageTopK(Integer requested, int fallback) {
        int topK = requested == null ? fallback : requested;
        topK = Math.max(topK, 0);
        topK = Math.min(topK, guardrails.getMaxMisCandidates());
        return topK;
    }

    private int[] splitTimeout(int timeoutMs, boolean stage1Enabled, boolean stage2Enabled) {
        if (timeoutMs <= 0) {
            return new int[] {0, 0};
        }
        if (stage1Enabled && stage2Enabled) {
            int stage1 = Math.max(1, (int) Math.floor(timeoutMs * STAGE1_TIMEOUT_RATIO));
            int stage2 = Math.max(1, timeoutMs - stage1);
            return new int[] {stage1, stage2};
        }
        if (stage1Enabled) {
            return new int[] {timeoutMs, 0};
        }
        if (stage2Enabled) {
            return new int[] {0, timeoutMs};
        }
        return new int[] {0, 0};
    }

    private StageResult executeStage1(
        ResolvedStage stage,
        List<EnrichedCandidate> candidates,
        String queryText,
        boolean debugEnabled,
        String traceId,
        String requestId,
        String traceparent
    ) {
        int in = candidates == null ? 0 : candidates.size();
        if (stage == null || !stage.enabled) {
            return StageResult.skipped(stage, in, "skip_disabled");
        }
        if (in == 0) {
            return StageResult.skipped(stage, in, "skip_no_candidates");
        }
        if (stage.topK <= 0) {
            return StageResult.skipped(stage, in, "skip_topk_zero");
        }

        List<ScoredCandidate> scored;
        String modelId;
        int cacheHits = 0;
        int cacheMisses = 0;

        if (!isBlank(stage.model) && misEligible(queryText, in, stage.timeoutMs)) {
            try {
                MisScoringResult misResult = scoreWithMis(
                    candidates,
                    queryText,
                    stage.timeoutMs,
                    stage.model,
                    debugEnabled,
                    traceId,
                    requestId,
                    traceparent
                );
                scored = misResult.scored;
                modelId = misResult.modelId;
                cacheHits = misResult.cacheHits;
                cacheMisses = misResult.cacheMisses;
            } catch (MisUnavailableException ex) {
                log.debug("Stage1 MIS unavailable; fallback to heuristic", ex);
                scored = buildScoredHeuristic(candidates);
                modelId = "rs_stage1_heuristic_v1";
            }
        } else {
            scored = buildScoredHeuristic(candidates);
            modelId = "rs_stage1_heuristic_v1";
        }

        sortScored(scored);
        int out = Math.min(stage.topK, scored.size());
        List<ScoredCandidate> topScored = new ArrayList<>(scored.subList(0, out));
        List<EnrichedCandidate> output = toEnrichedCandidates(topScored);

        return new StageResult(
            stage,
            true,
            modelId,
            "applied",
            in,
            out,
            cacheHits,
            cacheMisses,
            topScored,
            output
        );
    }

    private StageResult executeStage2(
        ResolvedStage stage,
        List<EnrichedCandidate> candidates,
        StageResult stage1Result,
        String queryText,
        boolean debugEnabled,
        String traceId,
        String requestId,
        String traceparent
    ) {
        int in = candidates == null ? 0 : candidates.size();
        if (stage == null || !stage.enabled) {
            return StageResult.skipped(stage, in, "skip_disabled");
        }
        if (in == 0) {
            return StageResult.skipped(stage, in, "skip_no_candidates");
        }
        if (stage.topK <= 0) {
            return StageResult.skipped(stage, in, "skip_topk_zero");
        }
        if (!misEligible(queryText, in, stage.timeoutMs)) {
            return StageResult.skipped(stage, in, "skip_not_eligible");
        }

        List<EnrichedCandidate> capped = new ArrayList<>(candidates.subList(0, Math.min(stage.topK, candidates.size())));
        try {
            MisScoringResult misResult = scoreWithMis(
                capped,
                queryText,
                stage.timeoutMs,
                stage.model,
                debugEnabled,
                traceId,
                requestId,
                traceparent
            );
            List<ScoredCandidate> scored = misResult.scored;
            sortScored(scored);
            int out = Math.min(stage.topK, scored.size());
            List<ScoredCandidate> topScored = new ArrayList<>(scored.subList(0, out));
            List<EnrichedCandidate> output = toEnrichedCandidates(topScored);
            return new StageResult(
                stage,
                true,
                misResult.modelId,
                "applied",
                in,
                out,
                misResult.cacheHits,
                misResult.cacheMisses,
                topScored,
                output
            );
        } catch (MisUnavailableException ex) {
            boolean timeout = isTimeoutError(ex);
            String reasonCode = timeout ? "timeout_degrade_to_stage1" : "error_degrade_to_stage1";
            List<ScoredCandidate> fallbackScored = stage1Result == null ? null : stage1Result.scored;
            if (fallbackScored == null || fallbackScored.isEmpty()) {
                fallbackScored = buildScoredHeuristic(candidates);
            }
            sortScored(fallbackScored);
            List<EnrichedCandidate> output = toEnrichedCandidates(fallbackScored);
            return new StageResult(
                stage,
                false,
                stage1Result == null ? null : stage1Result.modelId,
                reasonCode,
                in,
                fallbackScored.size(),
                0,
                0,
                fallbackScored,
                output
            );
        }
    }

    private boolean misEligible(String queryText, int candidatesUsed, int timeoutMs) {
        if (!misClient.isEnabled()) {
            return false;
        }
        if (timeoutMs <= 0) {
            return false;
        }
        if (candidatesUsed < guardrails.getMinCandidatesForMis()) {
            return false;
        }
        if (queryText != null && queryText.trim().length() < guardrails.getMinQueryLengthForMis()) {
            return false;
        }
        return true;
    }

    private MisScoringResult scoreWithMis(
        List<EnrichedCandidate> candidates,
        String queryText,
        int timeoutMs,
        String modelOverride,
        boolean debugEnabled,
        String traceId,
        String requestId,
        String traceparent
    ) {
        if (candidates == null || candidates.isEmpty()) {
            return new MisScoringResult(List.of(), modelOverride, 0, 0);
        }

        List<EnrichedCandidate> misCandidates = applyMisLimit(candidates);
        String resolvedModel = misClient.resolveModelId(modelOverride);
        String queryHash = queryHash(queryText);

        Map<String, Double> scoreByDocId = new LinkedHashMap<>();
        List<EnrichedCandidate> cacheMissCandidates = new ArrayList<>();
        int cacheHits = 0;
        int cacheMisses = 0;

        for (EnrichedCandidate candidate : misCandidates) {
            String cacheKey = buildCacheKey(resolvedModel, queryHash, candidate.getDocId());
            Optional<Double> cachedScore = safeCacheGet(cacheKey);
            if (cachedScore.isPresent()) {
                cacheHits++;
                meterRegistry.counter("rs_rerank_cache_hit_total").increment();
                scoreByDocId.put(candidate.getDocId(), cachedScore.get());
            } else {
                cacheMisses++;
                meterRegistry.counter("rs_rerank_cache_miss_total").increment();
                cacheMissCandidates.add(candidate);
            }
        }

        String modelId = resolvedModel;
        if (!cacheMissCandidates.isEmpty()) {
            meterRegistry.counter("rs_mis_calls_total").increment();
            List<RerankRequest.Candidate> requestCandidates = buildMisCandidates(cacheMissCandidates);
            MisScoreResponse scoreResponse = misClient.score(
                queryText,
                requestCandidates,
                timeoutMs,
                debugEnabled,
                modelOverride,
                traceId,
                requestId,
                traceparent
            );
            if (scoreResponse == null || scoreResponse.getScores() == null) {
                throw new MisUnavailableException("mis returned empty scores");
            }
            List<Double> scores = scoreResponse.getScores();
            if (scores.size() != cacheMissCandidates.size()) {
                throw new MisUnavailableException("mis score size mismatch");
            }
            for (int i = 0; i < cacheMissCandidates.size(); i++) {
                EnrichedCandidate candidate = cacheMissCandidates.get(i);
                double score = scores.get(i) == null ? 0.0 : scores.get(i);
                scoreByDocId.put(candidate.getDocId(), score);
                String cacheKey = buildCacheKey(resolvedModel, queryHash, candidate.getDocId());
                safeCachePut(cacheKey, score);
            }
            if (scoreResponse.getModel() != null && !scoreResponse.getModel().isBlank()) {
                modelId = scoreResponse.getModel();
            }
        }

        List<ScoredCandidate> scored = new ArrayList<>(misCandidates.size());
        for (EnrichedCandidate candidate : misCandidates) {
            double score = scoreByDocId.getOrDefault(candidate.getDocId(), 0.0);
            Integer lexRank = toInt(candidate.getRawFeatures().get("lex_rank"));
            Integer vecRank = toInt(candidate.getRawFeatures().get("vec_rank"));
            scored.add(new ScoredCandidate(candidate.getDocId(), score, lexRank, vecRank, candidate, null));
        }

        return new MisScoringResult(scored, modelId, cacheHits, cacheMisses);
    }

    private Optional<Double> safeCacheGet(String key) {
        try {
            return rerankScoreCache.get(key);
        } catch (RuntimeException ex) {
            log.debug("rerank cache get failed", ex);
            return Optional.empty();
        }
    }

    private void safeCachePut(String key, double score) {
        try {
            rerankScoreCache.put(key, score);
        } catch (RuntimeException ex) {
            log.debug("rerank cache put failed", ex);
        }
    }

    private String buildCacheKey(String modelId, String queryHash, String docId) {
        String resolvedModel = isBlank(modelId) ? "default" : modelId;
        String resolvedQueryHash = isBlank(queryHash) ? "na" : queryHash;
        String resolvedDocId = isBlank(docId) ? "na" : docId;
        return "rerank:" + resolvedModel + ":" + resolvedQueryHash + ":" + resolvedDocId;
    }

    private String queryHash(String queryText) {
        String normalized = queryText == null ? "" : queryText.trim().toLowerCase(Locale.ROOT).replaceAll("\\s+", " ");
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(normalized.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder(hashed.length * 2);
            for (byte b : hashed) {
                builder.append(String.format("%02x", b));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException e) {
            return Integer.toHexString(normalized.hashCode());
        }
    }

    private boolean isTimeoutError(Throwable throwable) {
        if (throwable == null) {
            return false;
        }
        String message = throwable.getMessage();
        if (message != null) {
            String lowered = message.toLowerCase(Locale.ROOT);
            if (lowered.contains("timeout") || lowered.contains("timed out")) {
                return true;
            }
        }
        return isTimeoutError(throwable.getCause());
    }

    private void sortScored(List<ScoredCandidate> scored) {
        if (scored == null) {
            return;
        }
        scored.sort(
            Comparator.comparingDouble(ScoredCandidate::score).reversed()
                .thenComparing(entry -> nullSafeRank(entry.lexRank()))
                .thenComparing(entry -> nullSafeRank(entry.vecRank()))
                .thenComparing(ScoredCandidate::docId)
        );
    }

    private List<EnrichedCandidate> toEnrichedCandidates(List<ScoredCandidate> scored) {
        if (scored == null || scored.isEmpty()) {
            return List.of();
        }
        List<EnrichedCandidate> candidates = new ArrayList<>(scored.size());
        for (ScoredCandidate entry : scored) {
            if (entry.enriched() != null) {
                candidates.add(entry.enriched());
            }
        }
        return candidates;
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

    private List<EnrichedCandidate> applyMisLimit(List<EnrichedCandidate> candidates) {
        if (candidates.size() > guardrails.getMaxMisCandidates()) {
            return new ArrayList<>(candidates.subList(0, guardrails.getMaxMisCandidates()));
        }
        return candidates;
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
            if (candidate.getSource() != null) {
                rerankCandidate.setDoc(candidate.getSource().getDoc());
                rerankCandidate.setTitle(candidate.getSource().getTitle());
                rerankCandidate.setAuthors(candidate.getSource().getAuthors());
                rerankCandidate.setSeries(candidate.getSource().getSeries());
                rerankCandidate.setPublisher(candidate.getSource().getPublisher());
            }
            RerankRequest.Features features = new RerankRequest.Features();
            Map<String, Object> raw = candidate.getRawFeatures();
            features.setLexRank(toInt(raw.get("lex_rank")));
            features.setVecRank(toInt(raw.get("vec_rank")));
            features.setRrfScore(toDouble(raw.get("rrf_score")));
            features.setFusedRank(toInt(raw.get("fused_rank")));
            features.setRrfRank(toInt(raw.get("rrf_rank")));
            features.setBm25Score(toDouble(raw.get("bm25_score")));
            features.setVecScore(toDouble(raw.get("vec_score")));
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
            debug.setRawFeatures(enriched.getRawFeatures());
        }
        debug.setReasonCodes(mergeReasons(reasonCodes, enriched == null ? null : enriched.getReasonCodes()));
        return debug;
    }

    private RerankResponse.DebugInfo buildResponseDebug(
        String modelId,
        List<String> reasonCodes,
        int candidatesIn,
        int candidatesUsed,
        int timeoutMs,
        boolean rerankApplied,
        RerankRequest request,
        Map<String, Object> stageDetails
    ) {
        FeatureSpec spec = featureSpecService.getSpec();
        RerankResponse.DebugInfo info = new RerankResponse.DebugInfo();
        info.setModelId(modelId);
        info.setFeatureSetVersion(spec == null ? null : spec.getFeatureSetVersion());
        info.setFeatureSpecVersion(spec == null ? null : spec.getFeatureSetVersion());
        info.setCandidatesIn(candidatesIn);
        info.setCandidatesUsed(candidatesUsed);
        info.setTimeoutMs(timeoutMs);
        info.setRerankApplied(rerankApplied);
        info.setReasonCodes(reasonCodes);
        info.setReplay(buildReplay(request));
        info.setStageDetails(stageDetails);
        return info;
    }

    private List<String> mergeReasons(List<String> base, List<String> extra) {
        if ((base == null || base.isEmpty()) && (extra == null || extra.isEmpty())) {
            return base;
        }
        List<String> merged = new ArrayList<>();
        if (base != null) {
            for (String reason : base) {
                if (reason != null && !merged.contains(reason)) {
                    merged.add(reason);
                }
            }
        }
        if (extra != null) {
            for (String reason : extra) {
                if (reason != null && !merged.contains(reason)) {
                    merged.add(reason);
                }
            }
        }
        return merged;
    }

    private Map<String, Object> buildReplay(RerankRequest request) {
        if (request == null) {
            return null;
        }
        Map<String, Object> replay = new LinkedHashMap<>();
        if (request.getQuery() != null) {
            Map<String, Object> query = new LinkedHashMap<>();
            query.put("text", request.getQuery().getText());
            replay.put("query", query);
        }
        if (request.getCandidates() != null) {
            List<Map<String, Object>> candidates = new ArrayList<>();
            for (RerankRequest.Candidate candidate : request.getCandidates()) {
                if (candidate == null) {
                    continue;
                }
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("doc_id", candidate.getDocId());
                if (candidate.getDoc() != null) {
                    entry.put("doc", candidate.getDoc());
                }
                if (candidate.getTitle() != null) {
                    entry.put("title", candidate.getTitle());
                }
                if (candidate.getAuthors() != null) {
                    entry.put("authors", candidate.getAuthors());
                }
                if (candidate.getSeries() != null) {
                    entry.put("series", candidate.getSeries());
                }
                if (candidate.getPublisher() != null) {
                    entry.put("publisher", candidate.getPublisher());
                }
                if (candidate.getFeatures() != null) {
                    entry.put("features", candidate.getFeatures());
                }
                candidates.add(entry);
            }
            replay.put("candidates", candidates);
        }
        if (request.getOptions() != null) {
            Map<String, Object> options = new LinkedHashMap<>();
            options.put("size", request.getOptions().getSize());
            options.put("timeout_ms", request.getOptions().getTimeoutMs());
            options.put("rerank", request.getOptions().getRerank());
            options.put("model", request.getOptions().getModel());
            options.put("debug", request.getOptions().getDebug());
            if (request.getOptions().getRerankConfig() != null) {
                options.put("rerank_config", request.getOptions().getRerankConfig());
            }
            replay.put("options", options);
        }
        return replay;
    }

    private Map<String, Object> stageDebugMap(StageResult stageResult) {
        Map<String, Object> stage = new LinkedHashMap<>();
        stage.put("enabled", stageResult.stage.enabled);
        stage.put("applied", stageResult.applied);
        stage.put("model", stageResult.modelId);
        stage.put("reason_code", stageResult.reasonCode);
        stage.put("timeout_ms", stageResult.stage.timeoutMs);
        stage.put("candidates_in", stageResult.candidatesIn);
        stage.put("candidates_out", stageResult.candidatesOut);
        stage.put("cache_hits", stageResult.cacheHits);
        stage.put("cache_misses", stageResult.cacheMisses);
        return stage;
    }

    private int nullSafeRank(Integer rank) {
        return rank == null ? Integer.MAX_VALUE : rank;
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
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

    private record MisScoringResult(List<ScoredCandidate> scored, String modelId, int cacheHits, int cacheMisses) {}

    private record StagePlan(ResolvedStage stage1, ResolvedStage stage2) {}

    private record ResolvedStage(boolean enabled, int topK, int timeoutMs, String model) {}

    private static class StageResult {
        private final ResolvedStage stage;
        private final boolean applied;
        private final String modelId;
        private final String reasonCode;
        private final int candidatesIn;
        private final int candidatesOut;
        private final int cacheHits;
        private final int cacheMisses;
        private final List<ScoredCandidate> scored;
        private final List<EnrichedCandidate> outputCandidates;

        private StageResult(
            ResolvedStage stage,
            boolean applied,
            String modelId,
            String reasonCode,
            int candidatesIn,
            int candidatesOut,
            int cacheHits,
            int cacheMisses,
            List<ScoredCandidate> scored,
            List<EnrichedCandidate> outputCandidates
        ) {
            this.stage = stage == null ? new ResolvedStage(false, 0, 0, null) : stage;
            this.applied = applied;
            this.modelId = modelId;
            this.reasonCode = reasonCode;
            this.candidatesIn = candidatesIn;
            this.candidatesOut = candidatesOut;
            this.cacheHits = cacheHits;
            this.cacheMisses = cacheMisses;
            this.scored = scored;
            this.outputCandidates = outputCandidates;
        }

        private static StageResult skipped(ResolvedStage stage, int candidatesIn, String reasonCode) {
            return new StageResult(stage, false, null, reasonCode, candidatesIn, 0, 0, 0, null, null);
        }
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
