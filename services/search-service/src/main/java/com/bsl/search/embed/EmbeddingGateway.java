package com.bsl.search.embed;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

@Component
public class EmbeddingGateway {
    private final RestTemplate restTemplate;
    private final EmbeddingProperties properties;

    public EmbeddingGateway(
        @Qualifier("embeddingRestTemplate") RestTemplate restTemplate,
        EmbeddingProperties properties
    ) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    public List<Double> embed(String text, Integer timeBudgetMs) {
        return embed(text, timeBudgetMs, null, null);
    }

    public List<Double> embed(String text, Integer timeBudgetMs, String traceId, String requestId) {
        if (text == null || text.isBlank()) {
            throw new EmbeddingUnavailableException("embed_empty_text");
        }
        if (properties.getBaseUrl() == null || properties.getBaseUrl().isBlank()) {
            throw new EmbeddingUnavailableException("embed_base_url_missing");
        }
        EmbeddingRequest request = new EmbeddingRequest();
        request.setModel(properties.getModel());
        request.setTexts(List.of(text));
        request.setNormalize(true);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        if (traceId != null && !traceId.isBlank()) {
            headers.add("x-trace-id", traceId);
        }
        if (requestId != null && !requestId.isBlank()) {
            headers.add("x-request-id", requestId);
        }
        HttpEntity<EmbeddingRequest> entity = new HttpEntity<>(request, headers);

        int retries = Math.max(0, properties.getRetryCount());
        for (int attempt = 0; attempt <= retries; attempt++) {
            try {
                RestTemplate client = restTemplateFor(timeBudgetMs);
                ResponseEntity<EmbeddingResponse> response = client.exchange(
                    buildUrl("/v1/embed"),
                    HttpMethod.POST,
                    entity,
                    EmbeddingResponse.class
                );
                EmbeddingResponse body = response.getBody();
                if (body == null || body.getVectors() == null || body.getVectors().isEmpty()) {
                    throw new EmbeddingUnavailableException("embed_empty_response");
                }
                List<Double> vector = body.getVectors().get(0);
                if (vector == null || vector.isEmpty()) {
                    throw new EmbeddingUnavailableException("embed_empty_vector");
                }
                return vector;
            } catch (ResourceAccessException e) {
                if (attempt >= retries) {
                    String reason = "embed_unavailable";
                    if (e.getCause() instanceof java.net.SocketTimeoutException) {
                        reason = "embed_timeout";
                    }
                    throw new EmbeddingUnavailableException(reason, e);
                }
            } catch (HttpStatusCodeException e) {
                if (attempt >= retries) {
                    String reason = "embed_http_" + e.getStatusCode().value();
                    throw new EmbeddingUnavailableException(reason, e);
                }
            }
        }
        throw new EmbeddingUnavailableException("embed_unavailable");
    }

    private String buildUrl(String path) {
        String base = properties.getBaseUrl();
        if (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        return base + path;
    }

    private RestTemplate restTemplateFor(Integer timeBudgetMs) {
        if (timeBudgetMs == null) {
            return restTemplate;
        }
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeBudgetMs);
        factory.setReadTimeout(timeBudgetMs);
        return new RestTemplate(factory);
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class EmbeddingRequest {
        private String model;
        private List<String> texts;
        private Boolean normalize;

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        public List<String> getTexts() {
            return texts;
        }

        public void setTexts(List<String> texts) {
            this.texts = texts;
        }

        public Boolean getNormalize() {
            return normalize;
        }

        public void setNormalize(Boolean normalize) {
            this.normalize = normalize;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class EmbeddingResponse {
        private String model;
        private List<List<Double>> vectors;

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        public List<List<Double>> getVectors() {
            return vectors;
        }

        public void setVectors(List<List<Double>> vectors) {
            this.vectors = vectors;
        }
    }
}
