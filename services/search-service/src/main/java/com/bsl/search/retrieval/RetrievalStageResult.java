package com.bsl.search.retrieval;

import java.util.Collections;
import java.util.List;
import java.util.Map;

public class RetrievalStageResult {
    private final List<String> docIds;
    private final Map<String, Double> scoresByDocId;
    private final Map<String, Object> queryDsl;
    private final boolean error;
    private final boolean timedOut;
    private final boolean skipped;
    private final long tookMs;
    private final String errorMessage;

    private RetrievalStageResult(
        List<String> docIds,
        Map<String, Double> scoresByDocId,
        Map<String, Object> queryDsl,
        boolean error,
        boolean timedOut,
        boolean skipped,
        long tookMs,
        String errorMessage
    ) {
        this.docIds = docIds == null ? List.of() : docIds;
        this.scoresByDocId = scoresByDocId == null ? Map.of() : scoresByDocId;
        this.queryDsl = queryDsl;
        this.error = error;
        this.timedOut = timedOut;
        this.skipped = skipped;
        this.tookMs = tookMs;
        this.errorMessage = errorMessage;
    }

    public static RetrievalStageResult success(
        List<String> docIds,
        Map<String, Double> scoresByDocId,
        Map<String, Object> queryDsl,
        long tookMs
    ) {
        return new RetrievalStageResult(docIds, scoresByDocId, queryDsl, false, false, false, tookMs, null);
    }

    public static RetrievalStageResult empty() {
        return new RetrievalStageResult(Collections.emptyList(), Map.of(), null, false, false, false, 0L, null);
    }

    public static RetrievalStageResult error(String message) {
        return new RetrievalStageResult(Collections.emptyList(), Map.of(), null, true, false, false, 0L, message);
    }

    public static RetrievalStageResult timedOut() {
        return new RetrievalStageResult(Collections.emptyList(), Map.of(), null, true, true, false, 0L, "timeout");
    }

    public static RetrievalStageResult skipped(String reason) {
        return new RetrievalStageResult(Collections.emptyList(), Map.of(), null, true, false, true, 0L, reason);
    }

    public List<String> getDocIds() {
        return docIds;
    }

    public Map<String, Double> getScoresByDocId() {
        return scoresByDocId;
    }

    public Map<String, Object> getQueryDsl() {
        return queryDsl;
    }

    public boolean isError() {
        return error;
    }

    public boolean isTimedOut() {
        return timedOut;
    }

    public boolean isSkipped() {
        return skipped;
    }

    public long getTookMs() {
        return tookMs;
    }

    public String getErrorMessage() {
        return errorMessage;
    }
}
