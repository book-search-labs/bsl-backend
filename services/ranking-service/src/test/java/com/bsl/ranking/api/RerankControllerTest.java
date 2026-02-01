package com.bsl.ranking.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RerankControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void healthReturnsOk() throws Exception {
        mockMvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void rerankOrdersDeterministically() throws Exception {
        String body = "{"
            + "\"query\":{\"text\":\"harry potter\"},"
            + "\"candidates\":["
            + "{\"doc_id\":\"b1\",\"features\":{\"rrf_score\":0.167,\"lex_rank\":1,\"vec_rank\":2,\"issued_year\":1999,\"volume\":1,\"edition_labels\":[\"recover\"]}},"
            + "{\"doc_id\":\"b2\",\"features\":{\"rrf_score\":0.150,\"lex_rank\":2,\"vec_rank\":1,\"issued_year\":2000,\"volume\":2,\"edition_labels\":[]}},"
            + "{\"doc_id\":\"b3\",\"features\":{\"rrf_score\":0.100,\"lex_rank\":3,\"vec_rank\":3,\"issued_year\":1985,\"volume\":0,\"edition_labels\":[]}}"
            + "],"
            + "\"options\":{\"size\":2}"
            + "}";

        mockMvc.perform(post("/rerank")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.model").value("toy_rerank_v1"))
            .andExpect(jsonPath("$.hits.length()").value(2))
            .andExpect(jsonPath("$.hits[0].doc_id").value("b1"))
            .andExpect(jsonPath("$.hits[1].doc_id").value("b2"));
    }

    @Test
    void rerankDebugIncludesReplay() throws Exception {
        String body = "{"
            + "\"query\":{\"text\":\"harry potter\"},"
            + "\"candidates\":["
            + "{\"doc_id\":\"b1\",\"features\":{\"rrf_score\":0.167,\"lex_rank\":1,\"vec_rank\":2,\"issued_year\":1999,\"volume\":1,\"edition_labels\":[\"recover\"]}}"
            + "],"
            + "\"options\":{\"size\":1,\"debug\":true}"
            + "}";

        mockMvc.perform(post("/rerank")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.debug.model_id").value("toy_rerank_v1"))
            .andExpect(jsonPath("$.hits[0].debug.raw_features.lex_rank").value(1))
            .andExpect(jsonPath("$.debug.replay.query.text").value("harry potter"))
            .andExpect(jsonPath("$.debug.replay.candidates[0].doc_id").value("b1"));
    }

    @Test
    void rerankRejectsInvalidInput() throws Exception {
        mockMvc.perform(post("/rerank")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"))
            .andExpect(jsonPath("$.trace_id").isNotEmpty())
            .andExpect(jsonPath("$.request_id").isNotEmpty());
    }
}
