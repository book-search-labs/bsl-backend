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
    void lexicalQueryUsesV2FieldsAndVisibilityFilter() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_doc_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode boolNode = root.path("query").path("bool");

                assertThat(root.path("track_total_hits").asBoolean()).isFalse();
                assertThat(boolNode.path("minimum_should_match").asInt()).isEqualTo(1);

                JsonNode filter = boolNode.path("filter");
                assertThat(filter.isArray()).isTrue();
                assertThat(filter.toString()).contains("\"is_hidden\":false");
                assertThat(filter.toString()).doesNotContain("\"language_code\":\"http://id.loc.gov/vocabulary/languages/kor\"");

                JsonNode should = boolNode.path("should");
                assertThat(should.isArray()).isTrue();
                assertThat(should.toString()).contains("http://id.loc.gov/vocabulary/languages/kor");
                JsonNode primaryShort = should.get(0).path("multi_match");
                assertThat(primaryShort.path("fields").toString()).contains("title_ko^9");
                assertThat(primaryShort.path("fields").toString()).contains("series_name^5");
                assertThat(primaryShort.path("fields").toString()).doesNotContain("author_names_ko");
                assertThat(should.toString()).contains("author_names_ko^0.6");
                assertThat(should.toString()).contains("author_names_ko.auto^4.0");
                assertThat(should.toString()).contains("title_ko.reading");

                boolean hasCompact = false;
                boolean hasBoolPrefix = false;
                boolean hasWildcard = false;
                for (JsonNode clause : should) {
                    JsonNode mm = clause.path("multi_match");
                    if (mm.isObject() && mm.path("fields").toString().contains("title_ko.compact")) {
                        hasCompact = true;
                    }
                    if (mm.isObject() && "bool_prefix".equals(mm.path("type").asText())) {
                        hasBoolPrefix = true;
                    }
                    if (clause.has("wildcard")) {
                        hasWildcard = true;
                    }
                }

                assertThat(hasCompact).isTrue();
                assertThat(hasBoolPrefix).isTrue();
                assertThat(hasWildcard).isFalse();
                assertThat(boolNode.path("must").toString()).contains("title_ko");
                assertThat(boolNode.path("must").toString()).contains("series_name");
                assertThat(boolNode.path("must").toString()).contains("author_names_ko.exact");
                assertThat(boolNode.path("must").toString()).contains("author_names_ko.auto^6");
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchLexicalDetailed("문화", 10, null, null, null, null, null, null, false);
        server.verify();
    }

    @Test
    void singleCharacterHangulKeepsKoreanLanguageHardFilter() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_doc_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode boolNode = root.path("query").path("bool");
                JsonNode filter = boolNode.path("filter");
                assertThat(filter.toString()).contains("\"language_code\":\"http://id.loc.gov/vocabulary/languages/kor\"");
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchLexicalDetailed("문", 10, null, null, null, null, null, null, false);
        server.verify();
    }

    @Test
    void singleTokenHangulNameDoesNotForceKoreanLanguageFilter() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_doc_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode boolNode = root.path("query").path("bool");
                JsonNode filter = boolNode.path("filter");

                assertThat(filter.isArray()).isTrue();
                assertThat(filter.toString()).contains("\"is_hidden\":false");
                assertThat(filter.toString()).doesNotContain("\"language_code\":\"http://id.loc.gov/vocabulary/languages/kor\"");
                assertThat(boolNode.path("must").toString()).contains("author_names_ko.exact");
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchLexicalDetailed("김혜경", 10, null, null, null, null, null, null, false);
        server.verify();
    }

    @Test
    void lexicalByDslAddsGlobalFilterContract() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_doc_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode filter = root.path("query").path("bool").path("filter");
                JsonNode should = root.path("query").path("bool").path("should");
                assertThat(filter.isArray()).isTrue();
                assertThat(filter.toString()).contains("\"is_hidden\":false");
                assertThat(filter.toString()).contains("\"language_code\":\"ko\"");
                assertThat(should.isArray()).isTrue();
                assertThat(should.toString()).contains("http://id.loc.gov/vocabulary/languages/kor");
                assertThat(root.path("query").path("bool").path("minimum_should_match").asInt()).isEqualTo(0);
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchLexicalByDslDetailed(
            Map.of("bool", Map.of("must", List.of(Map.of("match", Map.of("title_ko", "해리"))))),
            10,
            null,
            List.of(Map.of("term", Map.of("language_code", "ko"))),
            false
        );
        server.verify();
    }

    @Test
    void vectorQueryAddsVisibilityFilterAndDocIdSource() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/books_vec_read/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode filter = root.path("query").path("knn").path("embedding").path("filter").path("bool").path("filter");

                assertThat(root.path("track_total_hits").asBoolean()).isFalse();
                assertThat(root.path("_source").toString()).contains("doc_id");
                assertThat(filter.toString()).contains("\"is_hidden\":false");
                assertThat(filter.toString()).contains("\"kdc_code\":\"800\"");
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchVectorDetailed(
            List.of(0.1d, 0.2d),
            10,
            null,
            List.of(Map.of("term", Map.of("kdc_code", "800"))),
            false
        );
        server.verify();
    }

    @Test
    void chunkVectorQueryKeepsProvidedFiltersOnly() throws Exception {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        OpenSearchGateway gateway = new OpenSearchGateway(restTemplate, objectMapper, properties());

        server.expect(requestTo("http://localhost:9200/book_chunks_v1/_search"))
            .andExpect(method(POST))
            .andExpect(request -> {
                String body = ((MockClientHttpRequest) request).getBodyAsString(StandardCharsets.UTF_8);
                JsonNode root = objectMapper.readTree(body);
                JsonNode filter = root.path("query").path("knn").path("embedding").path("filter").path("bool").path("filter");
                assertThat(filter.toString()).contains("\"language_code\":\"ko\"");
                assertThat(filter.toString()).doesNotContain("is_hidden");
            })
            .andRespond(withSuccess("{\"hits\":{\"hits\":[]}}", MediaType.APPLICATION_JSON));

        gateway.searchChunkVectorDetailed(
            List.of(0.1d, 0.2d),
            10,
            null,
            List.of(Map.of("term", Map.of("language_code", "ko"))),
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
