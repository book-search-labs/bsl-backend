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

        List<HeuristicScorer.ScoreResult> scored = new ArrayList<>();
        for (RerankRequest.Candidate candidate : request.getCandidates()) {
            if (candidate == null || candidate.getDocId() == null || candidate.getDocId().isEmpty()) {
                continue;
            }
            HeuristicScorer.ScoreResult entry = HeuristicScorer.score(candidate);
            scored.add(entry);
        }

        scored.sort(
            Comparator.comparingDouble(HeuristicScorer.ScoreResult::score).reversed()
                .thenComparing(entry -> nullSafeRank(entry.lexRank()))
                .thenComparing(entry -> nullSafeRank(entry.vecRank()))
                .thenComparing(HeuristicScorer.ScoreResult::docId)
        );

        int limit = Math.min(size, scored.size());
        List<RerankResponse.Hit> hits = new ArrayList<>(limit);
        for (int i = 0; i < limit; i++) {
            HeuristicScorer.ScoreResult entry = scored.get(i);
            RerankResponse.Hit hit = new RerankResponse.Hit();
            hit.setDocId(entry.docId());
            hit.setScore(entry.score());
            hit.setRank(i + 1);
            hit.setDebug(HeuristicScorer.toDebug(entry));

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

    private int nullSafeRank(Integer rank) {
        return rank == null ? Integer.MAX_VALUE : rank;
    }
}
