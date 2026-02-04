package com.bsl.ranking.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.api.dto.RerankResponse;
import com.bsl.ranking.features.EnrichedCandidate;
import com.bsl.ranking.features.FeatureFetcher;
import com.bsl.ranking.features.FeatureSpec;
import com.bsl.ranking.features.FeatureSpecService;
import com.bsl.ranking.mis.MisClient;
import com.bsl.ranking.mis.MisUnavailableException;
import com.bsl.ranking.mis.dto.MisScoreResponse;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RerankServicePipelineTest {

    @Mock
    private MisClient misClient;

    @Mock
    private FeatureFetcher featureFetcher;

    @Mock
    private FeatureSpecService featureSpecService;

    private RerankService rerankService;
    private SimpleMeterRegistry meterRegistry;

    @BeforeEach
    void setUp() {
        RerankGuardrailsProperties guardrails = new RerankGuardrailsProperties();
        guardrails.setMaxCandidates(50);
        guardrails.setMaxTopN(20);
        guardrails.setMaxMisCandidates(20);
        guardrails.setMinCandidatesForMis(1);
        guardrails.setMinQueryLengthForMis(1);
        guardrails.setTimeoutMsMax(300);

        RerankCacheProperties cacheProperties = new RerankCacheProperties();
        cacheProperties.setEnabled(true);
        cacheProperties.setTtlSeconds(600);
        cacheProperties.setMaxEntries(1000);
        RerankScoreCache scoreCache = new RerankScoreCache(cacheProperties);

        meterRegistry = new SimpleMeterRegistry();
        rerankService = new RerankService(
            misClient,
            featureFetcher,
            featureSpecService,
            guardrails,
            scoreCache,
            meterRegistry
        );
        when(featureSpecService.getSpec()).thenReturn(new FeatureSpec("v1", "rs.fs.v1", List.of()));
    }

    @Test
    void usesScoreCacheToReduceMisCalls() {
        RerankRequest request = buildRequest("harry potter", false, true);
        when(featureFetcher.enrich(anyList(), anyString())).thenReturn(buildEnriched(request.getCandidates()));
        when(misClient.isEnabled()).thenReturn(true);
        when(misClient.resolveModelId(any())).thenReturn("rerank_ltr_baseline_v1");

        MisScoreResponse scoreResponse = new MisScoreResponse();
        scoreResponse.setModel("rerank_ltr_baseline_v1");
        scoreResponse.setScores(List.of(0.9, 0.8));
        when(misClient.score(anyString(), anyList(), anyInt(), anyBoolean(), any(), anyString(), anyString(), any()))
            .thenReturn(scoreResponse);

        RerankResponse first = rerankService.rerank(request, "trace-1", "req-1", null);
        RerankResponse second = rerankService.rerank(request, "trace-1", "req-2", null);

        verify(misClient, times(1)).score(anyString(), anyList(), anyInt(), anyBoolean(), any(), anyString(), anyString(), any());
        assertEquals("rerank_ltr_baseline_v1", first.getModel());
        assertEquals("rerank_ltr_baseline_v1", second.getModel());
        assertTrue(meterRegistry.counter("rs_rerank_cache_hit_total").count() >= 2.0);
    }

    @Test
    void degradesToStage1WhenStage2TimesOut() {
        RerankRequest request = buildRequest("harry potter", true, true);
        when(featureFetcher.enrich(anyList(), anyString())).thenReturn(buildEnriched(request.getCandidates()));
        when(misClient.isEnabled()).thenReturn(true);
        when(misClient.resolveModelId(any())).thenReturn("rerank_ltr_baseline_v1");
        when(misClient.score(anyString(), anyList(), anyInt(), anyBoolean(), any(), anyString(), anyString(), any()))
            .thenThrow(new MisUnavailableException("timeout"));

        RerankResponse response = rerankService.rerank(request, "trace-1", "req-1", null);

        assertEquals("rs_stage1_heuristic_v1", response.getModel());
        Object rawStage = response.getDebug().getStageDetails().get("stage2");
        assertTrue(rawStage instanceof Map<?, ?>);
        Map<?, ?> stage2 = (Map<?, ?>) rawStage;
        assertEquals("timeout_degrade_to_stage1", stage2.get("reason_code"));
    }

    private RerankRequest buildRequest(String query, boolean stage1Enabled, boolean stage2Enabled) {
        RerankRequest request = new RerankRequest();
        RerankRequest.Query requestQuery = new RerankRequest.Query();
        requestQuery.setText(query);
        request.setQuery(requestQuery);

        List<RerankRequest.Candidate> candidates = new ArrayList<>();
        candidates.add(buildCandidate("b1", 1, 2, 0.16, 1999));
        candidates.add(buildCandidate("b2", 2, 1, 0.15, 2000));
        request.setCandidates(candidates);

        RerankRequest.Options options = new RerankRequest.Options();
        options.setSize(2);
        options.setDebug(true);
        options.setTimeoutMs(200);

        RerankRequest.RerankConfig config = new RerankRequest.RerankConfig();
        RerankRequest.StageConfig stage1 = new RerankRequest.StageConfig();
        stage1.setEnabled(stage1Enabled);
        stage1.setTopK(2);
        config.setStage1(stage1);
        RerankRequest.StageConfig stage2 = new RerankRequest.StageConfig();
        stage2.setEnabled(stage2Enabled);
        stage2.setTopK(2);
        config.setStage2(stage2);
        options.setRerankConfig(config);
        request.setOptions(options);
        return request;
    }

    private RerankRequest.Candidate buildCandidate(
        String docId,
        int lexRank,
        int vecRank,
        double rrfScore,
        int issuedYear
    ) {
        RerankRequest.Candidate candidate = new RerankRequest.Candidate();
        candidate.setDocId(docId);
        candidate.setDoc("doc-" + docId);
        candidate.setTitle("title-" + docId);
        candidate.setAuthors(List.of("author-" + docId));
        candidate.setSeries("series-" + docId);
        candidate.setPublisher("publisher-" + docId);

        RerankRequest.Features features = new RerankRequest.Features();
        features.setLexRank(lexRank);
        features.setVecRank(vecRank);
        features.setRrfScore(rrfScore);
        features.setFusedRank(lexRank);
        features.setRrfRank(lexRank);
        features.setBm25Score(rrfScore * 10.0);
        features.setVecScore(rrfScore * 9.0);
        features.setIssuedYear(issuedYear);
        features.setVolume(1);
        features.setEditionLabels(List.of("recover"));
        candidate.setFeatures(features);
        return candidate;
    }

    private List<EnrichedCandidate> buildEnriched(List<RerankRequest.Candidate> candidates) {
        List<EnrichedCandidate> enriched = new ArrayList<>();
        for (RerankRequest.Candidate candidate : candidates) {
            Map<String, Object> raw = new LinkedHashMap<>();
            raw.put("lex_rank", candidate.getFeatures().getLexRank());
            raw.put("vec_rank", candidate.getFeatures().getVecRank());
            raw.put("rrf_score", candidate.getFeatures().getRrfScore());
            raw.put("fused_rank", candidate.getFeatures().getFusedRank());
            raw.put("bm25_score", candidate.getFeatures().getBm25Score());
            raw.put("vec_score", candidate.getFeatures().getVecScore());
            raw.put("issued_year", candidate.getFeatures().getIssuedYear());
            raw.put("volume", candidate.getFeatures().getVolume());

            Map<String, Double> transformed = new LinkedHashMap<>();
            transformed.put("lex_rank", candidate.getFeatures().getLexRank().doubleValue());
            transformed.put("vec_rank", candidate.getFeatures().getVecRank().doubleValue());
            transformed.put("rrf_score", candidate.getFeatures().getRrfScore());
            transformed.put("fused_rank", candidate.getFeatures().getFusedRank().doubleValue());
            transformed.put("bm25_score", candidate.getFeatures().getBm25Score());
            transformed.put("vec_score", candidate.getFeatures().getVecScore());
            transformed.put("query_len", 12.0);
            transformed.put("metadata_completeness", 1.0);

            enriched.add(new EnrichedCandidate(candidate.getDocId(), candidate, raw, transformed, List.of()));
        }
        return enriched;
    }
}
