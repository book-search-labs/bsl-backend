package com.bsl.search.retrieval;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchQueryResult;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class LexicalRetrieverTest {
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    @Mock
    private OpenSearchGateway openSearchGateway;

    @InjectMocks
    private LexicalRetriever lexicalRetriever;

    @Test
    void fallsBackToAuthorContainsWhenSingleTokenHangulReturnsNoLexicalHits() {
        when(
            openSearchGateway.searchLexicalDetailed(
                anyString(),
                anyInt(),
                any(),
                any(),
                any(),
                any(),
                any(),
                any(),
                anyBoolean()
            )
        ).thenReturn(new OpenSearchQueryResult(List.of(), Map.of("query", "lex"), Map.of()));
        when(openSearchGateway.searchAuthorContainsFallbackDetailed(anyString(), anyInt(), any(), anyList(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("nlk:CDM200700007"), Map.of("query", "author_contains"), Map.of()));

        RetrievalStageContext context = new RetrievalStageContext(
            "혜경",
            10,
            null,
            200,
            null,
            null,
            List.of(),
            null,
            null,
            true,
            false,
            "trace-1",
            "req-1"
        );

        RetrievalStageResult result = lexicalRetriever.retrieve(context);

        assertThat(result.isError()).isFalse();
        assertThat(result.getDocIds()).containsExactly("nlk:CDM200700007");
        assertThat(result.getQueryDsl()).isEqualTo(Map.of("query", "author_contains"));
        verify(openSearchGateway, never()).mgetSources(anyList(), any());
        verify(openSearchGateway).searchAuthorContainsFallbackDetailed("혜경", 10, 200, List.of(), false);
    }

    @Test
    void doesNotRunAuthorContainsFallbackWhenLexicalAlreadyHasHits() {
        when(
            openSearchGateway.searchLexicalDetailed(
                anyString(),
                anyInt(),
                any(),
                any(),
                any(),
                any(),
                any(),
                any(),
                anyBoolean()
            )
        ).thenReturn(new OpenSearchQueryResult(List.of("doc-1"), Map.of("query", "lex"), Map.of("doc-1", 1.0d)));

        when(openSearchGateway.mgetSources(List.of("doc-1"), 200))
            .thenReturn(Map.of("doc-1", sourceWithTitle("해리포터와 마법사의 돌")));

        RetrievalStageContext context = new RetrievalStageContext(
            "해리",
            10,
            null,
            200,
            null,
            null,
            List.of(),
            null,
            null,
            true,
            false,
            "trace-1",
            "req-1"
        );

        RetrievalStageResult result = lexicalRetriever.retrieve(context);

        assertThat(result.isError()).isFalse();
        assertThat(result.getDocIds()).containsExactly("doc-1");
        verify(openSearchGateway, never())
            .searchAuthorContainsFallbackDetailed(anyString(), anyInt(), any(), anyList(), anyBoolean());
    }

    @Test
    void runsAuthorContainsFallbackWhenTopLexicalHitsDoNotContainQueryInTitleOrAuthor() {
        when(
            openSearchGateway.searchLexicalDetailed(
                anyString(),
                anyInt(),
                any(),
                any(),
                any(),
                any(),
                any(),
                any(),
                anyBoolean()
            )
        ).thenReturn(new OpenSearchQueryResult(List.of("doc-x"), Map.of("query", "lex"), Map.of("doc-x", 1.0d)));
        when(openSearchGateway.mgetSources(List.of("doc-x"), 200))
            .thenReturn(Map.of("doc-x", sourceWithAuthor("호춘혜")));
        when(openSearchGateway.searchAuthorContainsFallbackDetailed(anyString(), anyInt(), any(), anyList(), anyBoolean()))
            .thenReturn(new OpenSearchQueryResult(List.of("nlk:CDM200700007"), Map.of("query", "author_contains"), Map.of()));

        RetrievalStageContext context = new RetrievalStageContext(
            "혜경",
            10,
            null,
            200,
            null,
            null,
            List.of(),
            null,
            null,
            true,
            false,
            "trace-1",
            "req-1"
        );

        RetrievalStageResult result = lexicalRetriever.retrieve(context);

        assertThat(result.isError()).isFalse();
        assertThat(result.getDocIds()).containsExactly("nlk:CDM200700007");
        verify(openSearchGateway).mgetSources(List.of("doc-x"), 200);
        verify(openSearchGateway).searchAuthorContainsFallbackDetailed("혜경", 10, 200, List.of(), false);
    }

    private ObjectNode sourceWithAuthor(String author) {
        ObjectNode node = OBJECT_MAPPER.createObjectNode();
        node.putArray("author_names_ko").add(author);
        return node;
    }

    private ObjectNode sourceWithTitle(String title) {
        ObjectNode node = OBJECT_MAPPER.createObjectNode();
        node.put("title_ko", title);
        return node;
    }
}
