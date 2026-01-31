package com.bsl.ranking.features;

import com.bsl.ranking.api.dto.RerankRequest;
import java.util.List;
import java.util.Map;

public class EnrichedCandidate {
    private final String docId;
    private final RerankRequest.Candidate source;
    private final Map<String, Object> rawFeatures;
    private final Map<String, Double> features;
    private final List<String> reasonCodes;

    public EnrichedCandidate(
        String docId,
        RerankRequest.Candidate source,
        Map<String, Object> rawFeatures,
        Map<String, Double> features,
        List<String> reasonCodes
    ) {
        this.docId = docId;
        this.source = source;
        this.rawFeatures = rawFeatures;
        this.features = features;
        this.reasonCodes = reasonCodes;
    }

    public String getDocId() {
        return docId;
    }

    public RerankRequest.Candidate getSource() {
        return source;
    }

    public Map<String, Object> getRawFeatures() {
        return rawFeatures;
    }

    public Map<String, Double> getFeatures() {
        return features;
    }

    public List<String> getReasonCodes() {
        return reasonCodes;
    }
}
