package com.bsl.ranking.service;

import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.api.dto.RerankResponse;
import com.bsl.ranking.mis.MisClient;
import com.bsl.ranking.mis.MisUnavailableException;
import com.bsl.ranking.mis.dto.MisScoreResponse;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class RerankService {
    private static final Logger log = LoggerFactory.getLogger(RerankService.class);
    private static final int DEFAULT_SIZE = 10;

    private final MisClient misClient;
    private final ToyRerankService fallbackService;

    public RerankService(MisClient misClient, ToyRerankService fallbackService) {
        this.misClient = misClient;
        this.fallbackService = fallbackService;
    }

    public RerankResponse rerank(RerankRequest request, String traceId, String requestId) {
        if (misClient.isEnabled()) {
            try {
                RerankResponse response = rerankWithMis(request, traceId, requestId);
                if (response != null) {
                    return response;
                }
            } catch (MisUnavailableException e) {
                log.debug("MIS unavailable, falling back to heuristic scorer", e);
            }
        }
        return fallbackService.rerank(request, traceId, requestId);
    }

    private RerankResponse rerankWithMis(RerankRequest request, String traceId, String requestId) {
        long started = System.nanoTime();
        List<RerankRequest.Candidate> candidates = collectCandidates(request);
        if (candidates.isEmpty()) {
            throw new MisUnavailableException("no candidates to score");
        }

        String queryText = request.getQuery() == null ? null : request.getQuery().getText();
        MisScoreResponse scoreResponse = misClient.score(queryText, candidates, traceId, requestId);
        if (scoreResponse == null || scoreResponse.getScores() == null) {
            throw new MisUnavailableException("mis returned empty scores");
        }

        List<Double> scores = scoreResponse.getScores();
        if (scores.size() != candidates.size()) {
            throw new MisUnavailableException("mis score size mismatch");
        }

        List<ScoredCandidate> scored = new ArrayList<>(candidates.size());
        for (int i = 0; i < candidates.size(); i++) {
            RerankRequest.Candidate candidate = candidates.get(i);
            double score = scores.get(i) == null ? 0.0 : scores.get(i);
            Integer lexRank = candidate.getFeatures() == null ? null : candidate.getFeatures().getLexRank();
            Integer vecRank = candidate.getFeatures() == null ? null : candidate.getFeatures().getVecRank();
            scored.add(new ScoredCandidate(candidate.getDocId(), score, lexRank, vecRank));
        }

        scored.sort(
            Comparator.comparingDouble(ScoredCandidate::score).reversed()
                .thenComparing(entry -> nullSafeRank(entry.lexRank()))
                .thenComparing(entry -> nullSafeRank(entry.vecRank()))
                .thenComparing(ScoredCandidate::docId)
        );

        int size = resolveSize(request);
        int limit = Math.min(size, scored.size());
        List<RerankResponse.Hit> hits = new ArrayList<>(limit);
        for (int i = 0; i < limit; i++) {
            ScoredCandidate entry = scored.get(i);
            RerankResponse.Hit hit = new RerankResponse.Hit();
            hit.setDocId(entry.docId());
            hit.setScore(entry.score());
            hit.setRank(i + 1);
            hits.add(hit);
        }

        long tookMs = (System.nanoTime() - started) / 1_000_000L;
        RerankResponse response = new RerankResponse();
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs(tookMs);
        response.setModel(scoreResponse.getModel() == null ? "mis" : scoreResponse.getModel());
        response.setHits(hits);
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

    private int resolveSize(RerankRequest request) {
        int size = DEFAULT_SIZE;
        if (request.getOptions() != null && request.getOptions().getSize() != null) {
            size = Math.max(request.getOptions().getSize(), 0);
        }
        return size;
    }

    private int nullSafeRank(Integer rank) {
        return rank == null ? Integer.MAX_VALUE : rank;
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private record ScoredCandidate(String docId, double score, Integer lexRank, Integer vecRank) {}
}
