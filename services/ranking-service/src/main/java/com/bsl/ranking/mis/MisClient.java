package com.bsl.ranking.mis;

import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.mis.dto.MisScoreRequest;
import com.bsl.ranking.mis.dto.MisScoreResponse;
import java.util.ArrayList;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

@Component
public class MisClient {
    private final RestTemplate restTemplate;
    private final MisProperties properties;

    public MisClient(@Qualifier("misRestTemplate") RestTemplate restTemplate, MisProperties properties) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    public boolean isEnabled() {
        return properties.isEnabled();
    }

    public String resolveModelId(String modelOverride) {
        if (modelOverride != null && !modelOverride.isBlank()) {
            return modelOverride;
        }
        if (properties.getModelId() != null && !properties.getModelId().isBlank()) {
            return properties.getModelId();
        }
        return "mis";
    }

    public MisScoreResponse score(
        String queryText,
        List<RerankRequest.Candidate> candidates,
        int timeoutMs,
        boolean returnDebug,
        String modelOverride,
        String traceId,
        String requestId,
        String traceparent
    ) {
        if (!properties.isEnabled()) {
            throw new MisUnavailableException("mis disabled");
        }
        if (properties.getBaseUrl() == null || properties.getBaseUrl().isBlank()) {
            throw new MisUnavailableException("mis baseUrl not configured");
        }

        MisScoreRequest scoreRequest = new MisScoreRequest();
        scoreRequest.setVersion("v1");
        scoreRequest.setTraceId(traceId);
        scoreRequest.setRequestId(requestId);
        if (modelOverride != null && !modelOverride.isBlank()) {
            scoreRequest.setModel(modelOverride);
        } else {
            scoreRequest.setModel(properties.getModelId());
        }
        scoreRequest.setTask(properties.getTask());

        MisScoreRequest.Options options = new MisScoreRequest.Options();
        int resolvedTimeout = timeoutMs > 0 ? timeoutMs : properties.getTimeoutMs();
        options.setTimeoutMs(resolvedTimeout);
        options.setReturnDebug(returnDebug);
        scoreRequest.setOptions(options);

        List<MisScoreRequest.Pair> pairs = new ArrayList<>();
        for (RerankRequest.Candidate candidate : candidates) {
            if (candidate == null) {
                continue;
            }
            MisScoreRequest.Pair pair = new MisScoreRequest.Pair();
            pair.setPairId(candidate.getDocId());
            pair.setQuery(queryText == null ? "" : queryText);
            pair.setDocId(candidate.getDocId());
            String docText = candidate.getDoc();
            if (docText == null || docText.isBlank()) {
                docText = candidate.getDocId();
            }
            pair.setDoc(docText);

            MisScoreRequest.Features features = new MisScoreRequest.Features();
            if (candidate.getFeatures() != null) {
                features.setLexRank(candidate.getFeatures().getLexRank());
                features.setVecRank(candidate.getFeatures().getVecRank());
                features.setRrfScore(candidate.getFeatures().getRrfScore());
                features.setIssuedYear(candidate.getFeatures().getIssuedYear());
                features.setVolume(candidate.getFeatures().getVolume());
                features.setEditionLabels(candidate.getFeatures().getEditionLabels());
            }
            pair.setFeatures(features);
            pairs.add(pair);
        }
        scoreRequest.setPairs(pairs);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.add("x-trace-id", traceId);
        headers.add("x-request-id", requestId);
        if (traceparent != null && !traceparent.isBlank()) {
            headers.add("traceparent", traceparent);
        }
        HttpEntity<MisScoreRequest> entity = new HttpEntity<>(scoreRequest, headers);

        try {
            ResponseEntity<MisScoreResponse> response = restTemplate.exchange(
                buildUrl("/v1/score"),
                HttpMethod.POST,
                entity,
                MisScoreResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException e) {
            throw new MisUnavailableException("mis unavailable", e);
        } catch (HttpStatusCodeException e) {
            throw new MisUnavailableException("mis error: " + e.getStatusCode(), e);
        }
    }

    private String buildUrl(String path) {
        String base = properties.getBaseUrl();
        if (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        return base + path;
    }
}
