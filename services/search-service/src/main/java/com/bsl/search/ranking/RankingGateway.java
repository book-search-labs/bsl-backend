package com.bsl.search.ranking;

import com.bsl.search.ranking.dto.RerankRequest;
import com.bsl.search.ranking.dto.RerankResponse;
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
public class RankingGateway {
    private final RestTemplate restTemplate;
    private final RankingProperties properties;

    public RankingGateway(
        @Qualifier("rankingRestTemplate") RestTemplate restTemplate,
        RankingProperties properties
    ) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    public RerankResponse rerank(
        String queryText,
        List<RerankRequest.Candidate> candidates,
        int size,
        String traceId,
        String requestId,
        String traceparent
    ) {
        RerankRequest request = new RerankRequest();
        RerankRequest.Query query = new RerankRequest.Query();
        query.setText(queryText);
        request.setQuery(query);
        request.setCandidates(candidates);
        RerankRequest.Options options = new RerankRequest.Options();
        options.setSize(size);
        request.setOptions(options);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.add("x-trace-id", traceId);
        headers.add("x-request-id", requestId);
        if (traceparent != null && !traceparent.isBlank()) {
            headers.add("traceparent", traceparent);
        }

        HttpEntity<RerankRequest> entity = new HttpEntity<>(request, headers);

        try {
            ResponseEntity<RerankResponse> response = restTemplate.exchange(
                buildUrl("/rerank"),
                HttpMethod.POST,
                entity,
                RerankResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException e) {
            throw new RankingUnavailableException("Ranking service unavailable", e);
        } catch (HttpStatusCodeException e) {
            throw new RankingUnavailableException("Ranking service error: " + e.getStatusCode(), e);
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
