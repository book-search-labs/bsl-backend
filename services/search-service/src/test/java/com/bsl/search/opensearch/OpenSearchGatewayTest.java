package com.bsl.search.opensearch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.http.client.MockClientHttpRequest;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class OpenSearchGatewayTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void lexicalQueryAddsContainsFallbackForKoreanCompoundToken() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_doc_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode boolNode = root.path("query").path("bool");

                assertThat(boolNode.path("minimum_should_match").asInt()).isEqualTo(1);
                JsonNode should = boolNode.path("should");
                assertThat(should.isArray()).isTrue();

                boolean hasNgramFallback = false;
                boolean hasContainsFallback = false;
                for (JsonNode clause : should) {
                    JsonNode mm = clause.path("multi_match");
                    if (mm.isObject() && mm.path("fields").toString().contains("title_ko.ngram")) {
                        hasNgramFallback = true;
                    }
                    JsonNode wildcard = clause.path("wildcard").path("title_ko.raw");
                    if (wildcard.isObject() && "*영어교육*".equals(wildcard.path("value").asText())) {
                        hasContainsFallback = true;
                    }
                }

                assertThat(hasNgramFallback).isTrue();
                assertThat(hasContainsFallback).isTrue();
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchLexicalDetailed("영어교육", 10, null, null, null, null, null, null, false);
        server.verify();
    }

    @Test
    void lexicalQuerySkipsContainsFallbackForOneCharacterQuery() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_doc_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode should = root.path("query").path("bool").path("should");

                boolean hasWildcard = false;
                for (JsonNode clause : should) {
                    if (clause.path("wildcard").has("title_ko.raw")) {
                        hasWildcard = true;
                        break;
                    }
                }
                assertThat(hasWildcard).isFalse();
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchLexicalDetailed("영", 10, null, null, null, null, null, null, false);
        server.verify();
    }

    @Test
    void matchAllWithKdcFilterDoesNotUseScriptSort() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_doc_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode sort = root.path("sort");
                assertThat(sort.isMissingNode()).isTrue();
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchMatchAllDetailed(
            10,
            null,
            List.of(Map.of("terms", Map.of("kdc_path_codes", List.of("700")))),
            false
        );
        server.verify();
    }

    private OpenSearchProperties properties() {
        OpenSearchProperties properties = new OpenSearchProperties();
        properties.setBaseUrl("http://localhost:9200");
        properties.setDocIndex("books_doc_read");
        properties.setVecIndex("books_vec_read");
        properties.setChunkIndex("book_chunks_v1");
        return properties;
    }
}
