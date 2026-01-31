package com.bsl.search.embed;

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
        if (text == null || text.isBlank()) {
            throw new EmbeddingUnavailableException("query text is empty");
        }
        if (properties.getBaseUrl() == null || properties.getBaseUrl().isBlank()) {
            throw new EmbeddingUnavailableException("embedding.base-url is not configured");
        }
        EmbeddingRequest request = new EmbeddingRequest();
        request.setModel(properties.getModel());
        request.setTexts(List.of(text));

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<EmbeddingRequest> entity = new HttpEntity<>(request, headers);

        try {
            RestTemplate client = restTemplateFor(timeBudgetMs);
            ResponseEntity<EmbeddingResponse> response = client.exchange(
                buildUrl("/embed"),
                HttpMethod.POST,
                entity,
                EmbeddingResponse.class
            );
            EmbeddingResponse body = response.getBody();
            if (body == null || body.getVectors() == null || body.getVectors().isEmpty()) {
                throw new EmbeddingUnavailableException("embedding response is empty");
            }
            List<Double> vector = body.getVectors().get(0);
            if (vector == null || vector.isEmpty()) {
                throw new EmbeddingUnavailableException("embedding vector is empty");
            }
            return vector;
        } catch (ResourceAccessException e) {
            throw new EmbeddingUnavailableException("embedding service unavailable", e);
        } catch (HttpStatusCodeException e) {
            throw new EmbeddingUnavailableException("embedding service error: " + e.getStatusCode(), e);
        }
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

    public static class EmbeddingRequest {
        private String model;
        private List<String> texts;

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
    }

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
