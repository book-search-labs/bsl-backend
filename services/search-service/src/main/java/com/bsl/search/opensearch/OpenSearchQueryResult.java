package com.bsl.search.opensearch;

import java.util.Collections;
import java.util.List;
import java.util.Map;

public class OpenSearchQueryResult {
    private final List<String> docIds;
    private final Map<String, Object> queryDsl;

    public OpenSearchQueryResult(List<String> docIds, Map<String, Object> queryDsl) {
        this.docIds = docIds == null ? Collections.emptyList() : docIds;
        this.queryDsl = queryDsl;
    }

    public List<String> getDocIds() {
        return docIds;
    }

    public Map<String, Object> getQueryDsl() {
        return queryDsl;
    }
}
