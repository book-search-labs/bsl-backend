package com.bsl.autocomplete.opensearch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.http.client.MockClientHttpRequest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class OpenSearchGatewayTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void suggestionQueryIncludesGaussDecayAndVisibilityContract() throws Exception {
        OpenSearchGateway gateway = new OpenSearchGateway(objectMapper, properties());
        RestTemplate restTemplate = (RestTemplate) ReflectionTestUtils.getField(gateway, "restTemplate");
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();

        server.expect(requestTo("http://localhost:9200/ac_candidates_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode boolNode = root.path("query").path("function_score").path("query").path("bool");
                JsonNode functions = root.path("query").path("function_score").path("functions");

                assertThat(root.path("track_total_hits").asBoolean()).isFalse();
                assertThat(boolNode.path("filter").toString()).contains("\"is_blocked\":false");
                assertThat(boolNode.path("should").toString()).contains("\"type\":\"bool_prefix\"");
                assertThat(boolNode.path("should").toString()).contains("text.compact");
                assertThat(functions.toString()).contains("\"gauss\"");
                assertThat(functions.toString()).contains("\"last_seen_at\"");
                assertThat(functions.toString()).contains("\"scale\":\"14d\"");
                assertThat(functions.toString()).contains("\"decay\":0.5");
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchSuggestions("해리", 10);
        server.verify();
    }

    @Test
    void trendingQueryIncludesGaussDecay() throws Exception {
        OpenSearchGateway gateway = new OpenSearchGateway(objectMapper, properties());
        RestTemplate restTemplate = (RestTemplate) ReflectionTestUtils.getField(gateway, "restTemplate");
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();

        server.expect(requestTo("http://localhost:9200/ac_candidates_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode boolNode = root.path("query").path("function_score").path("query").path("bool");
                JsonNode functions = root.path("query").path("function_score").path("functions");

                assertThat(root.path("track_total_hits").asBoolean()).isFalse();
                assertThat(boolNode.path("must").toString()).contains("match_all");
                assertThat(boolNode.path("filter").toString()).contains("\"is_blocked\":false");
                assertThat(functions.toString()).contains("\"gauss\"");
                assertThat(functions.toString()).contains("\"last_seen_at\"");
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchTrendingSuggestions(10);
        server.verify();
    }

    private OpenSearchProperties properties() {
        OpenSearchProperties properties = new OpenSearchProperties();
        properties.setUrl("http://localhost:9200");
        properties.setIndex("ac_candidates_read");
        properties.setTimeoutMs(1000);
        return properties;
    }
}
