package com.bsl.bff.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.bff.config.DownstreamProperties;
import com.bsl.bff.security.AuthContext;
import com.bsl.bff.security.AuthContextHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class QueryServiceClientTest {

    @AfterEach
    void tearDown() {
        AuthContextHolder.clear();
    }

    @Test
    void fetchQueryContextSendsJsonBody() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        ObjectMapper mapper = new ObjectMapper();
        QueryServiceClient client = new QueryServiceClient(restTemplate, downstream("http://localhost:8001"), mapper);

        server.expect(requestTo("http://localhost:8001/query/prepare"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.CONTENT_TYPE, org.hamcrest.Matchers.containsString(MediaType.APPLICATION_JSON_VALUE)))
            .andExpect(content().json("{\"query\":{\"raw\":\"해리포터\"}}"))
            .andRespond(withSuccess("{\"version\":\"v1.1\"}", MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchQueryContext("해리포터", null);
        assertThat(response.path("version").asText()).isEqualTo("v1.1");
        server.verify();
    }

    @Test
    void chatForwardsUserAndAdminHeadersWhenAuthContextExists() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        ObjectMapper mapper = new ObjectMapper();
        QueryServiceClient client = new QueryServiceClient(restTemplate, downstream("http://localhost:8001"), mapper);
        ObjectNode ok = mapper.createObjectNode();
        ok.put("status", "ok");
        when(restTemplate.exchange(eq("http://localhost:8001/chat"), eq(HttpMethod.POST), any(HttpEntity.class), eq(com.fasterxml.jackson.databind.JsonNode.class)))
            .thenReturn(ResponseEntity.ok(ok));

        AuthContextHolder.set(new AuthContext("101", "42"));
        client.chat(java.util.Map.of("message", java.util.Map.of("role", "user", "content", "배송 상태")), null);

        ArgumentCaptor<HttpEntity> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(eq("http://localhost:8001/chat"), eq(HttpMethod.POST), entityCaptor.capture(), eq(com.fasterxml.jackson.databind.JsonNode.class));
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-user-id")).isEqualTo("101");
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-admin-id")).isEqualTo("42");
    }

    @Test
    void chatRecommendExperimentSnapshotForwardsAuthHeaders() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        ObjectMapper mapper = new ObjectMapper();
        QueryServiceClient client = new QueryServiceClient(restTemplate, downstream("http://localhost:8001"), mapper);
        ObjectNode ok = mapper.createObjectNode();
        ok.put("status", "ok");
        when(restTemplate.exchange(eq("http://localhost:8001/internal/chat/recommend/experiment"), eq(HttpMethod.GET), any(HttpEntity.class), eq(com.fasterxml.jackson.databind.JsonNode.class)))
            .thenReturn(ResponseEntity.ok(ok));

        AuthContextHolder.set(new AuthContext("101", "42"));
        client.chatRecommendExperimentSnapshot(null);

        ArgumentCaptor<HttpEntity> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(eq("http://localhost:8001/internal/chat/recommend/experiment"), eq(HttpMethod.GET), entityCaptor.capture(), eq(com.fasterxml.jackson.databind.JsonNode.class));
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-user-id")).isEqualTo("101");
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-admin-id")).isEqualTo("42");
    }

    @Test
    void resetChatRecommendExperimentForwardsAuthHeaders() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        ObjectMapper mapper = new ObjectMapper();
        QueryServiceClient client = new QueryServiceClient(restTemplate, downstream("http://localhost:8001"), mapper);
        ObjectNode ok = mapper.createObjectNode();
        ok.put("status", "ok");
        when(restTemplate.exchange(eq("http://localhost:8001/internal/chat/recommend/experiment/reset"), eq(HttpMethod.POST), any(HttpEntity.class), eq(com.fasterxml.jackson.databind.JsonNode.class)))
            .thenReturn(ResponseEntity.ok(ok));

        AuthContextHolder.set(new AuthContext("101", "42"));
        client.resetChatRecommendExperiment(null, java.util.Map.of("clear_overrides", true));

        ArgumentCaptor<HttpEntity> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(eq("http://localhost:8001/internal/chat/recommend/experiment/reset"), eq(HttpMethod.POST), entityCaptor.capture(), eq(com.fasterxml.jackson.databind.JsonNode.class));
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-user-id")).isEqualTo("101");
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-admin-id")).isEqualTo("42");
        Object body = entityCaptor.getValue().getBody();
        assertThat(body).isInstanceOf(java.util.Map.class);
        assertThat(((java.util.Map<?, ?>) body).get("clear_overrides")).isEqualTo(Boolean.TRUE);
    }

    @Test
    void chatRecommendExperimentConfigForwardsAuthHeadersAndBody() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        ObjectMapper mapper = new ObjectMapper();
        QueryServiceClient client = new QueryServiceClient(restTemplate, downstream("http://localhost:8001"), mapper);
        ObjectNode ok = mapper.createObjectNode();
        ok.put("status", "ok");
        when(restTemplate.exchange(eq("http://localhost:8001/internal/chat/recommend/experiment/config"), eq(HttpMethod.POST), any(HttpEntity.class), eq(com.fasterxml.jackson.databind.JsonNode.class)))
            .thenReturn(ResponseEntity.ok(ok));

        AuthContextHolder.set(new AuthContext("101", "42"));
        client.chatRecommendExperimentConfig(null, java.util.Map.of("overrides", java.util.Map.of("diversity_percent", 70)));

        ArgumentCaptor<HttpEntity> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(eq("http://localhost:8001/internal/chat/recommend/experiment/config"), eq(HttpMethod.POST), entityCaptor.capture(), eq(com.fasterxml.jackson.databind.JsonNode.class));
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-user-id")).isEqualTo("101");
        assertThat(entityCaptor.getValue().getHeaders().getFirst("x-admin-id")).isEqualTo("42");
        Object body = entityCaptor.getValue().getBody();
        assertThat(body).isInstanceOf(java.util.Map.class);
        assertThat(((java.util.Map<?, ?>) body).get("overrides")).isNotNull();
    }

    private DownstreamProperties downstream(String queryBaseUrl) {
        DownstreamProperties properties = new DownstreamProperties();
        DownstreamProperties.ServiceProperties query = new DownstreamProperties.ServiceProperties();
        query.setBaseUrl(queryBaseUrl);
        properties.setQueryService(query);
        return properties;
    }
}
