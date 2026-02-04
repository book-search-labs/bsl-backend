package com.bsl.search.opensearch;

import java.util.Collections;
import java.util.List;
import java.util.Map;

public class OpenSearchQueryResult {
    private final List<String> docIds;
    private final Map<String, Object> queryDsl;
    private final Map<String, Double> scoresByDocId;

    public OpenSearchQueryResult(List<String> docIds, Map<String, Object> queryDsl, Map<String, Double> scoresByDocId) {
        this.docIds = docIds == null ? Collections.emptyList() : docIds;
        this.queryDsl = queryDsl;
        this.scoresByDocId = scoresByDocId == null ? Collections.emptyMap() : scoresByDocId;
    }

    public List<String> getDocIds() {
        return docIds;
    }

    public Map<String, Object> getQueryDsl() {
        return queryDsl;
    }

    public Map<String, Double> getScoresByDocId() {
        return scoresByDocId;
    }
}
